"""Fixed topology neural genomes and reproducible elitist genetic evolution."""
import numpy as np


def genome_size(sensors=7, hidden_size=8):
    return (sensors + 2) * hidden_size + (hidden_size + 1) * 2


def initial_population(config, rng):
    size = genome_size(config.sensors, config.hidden_size)
    population = rng.normal(0, .65, (config.population, size)).astype(np.float32)
    # Biases, like every other parameter, are random and evolved. No controller
    # or track geometry is encoded in these initial weights.
    inputs = config.sensors + 1
    population[:, inputs * config.hidden_size:(inputs + 1) * config.hidden_size] *= .4
    population[:, -2:] *= .4
    return population


def next_generation(population, scores, config, rng, stagnation=0):
    if not np.isfinite(scores).all():
        raise ValueError("Nonfinite fitness is not eligible for selection")
    count = len(population)
    ranking = np.argsort(-np.asarray(scores), kind="stable")
    elite_count = max(1, int(count * config.elite_fraction))
    output = np.empty_like(population)
    output[:elite_count] = population[ranking[:elite_count]]
    pool = ranking[:max(elite_count + 1, count // 4)]
    children_count = count - elite_count
    tournaments = rng.integers(0, len(pool), (2, children_count, 3))
    parents = pool[tournaments.min(axis=2)]
    first, second = population[parents[0]], population[parents[1]]
    mask = rng.random(first.shape) < .5
    children = np.where(mask, first, second)
    factor = 1 + min(2., stagnation / config.stagnation_generations)
    effective_rate = min(.65, config.mutation_rate * factor)
    effective_strength = config.mutation_strength * factor
    mutations = rng.random(children.shape) < effective_rate
    children += (rng.normal(0, effective_strength, children.shape) * mutations).astype(np.float32)
    output[elite_count:] = np.clip(children, -6, 6)
    immigrant_count = min(children_count, max(1, int(count * (.025 if stagnation < config.stagnation_generations else .1))))
    output[-immigrant_count:] = initial_population(config, rng)[:immigrant_count]
    return output, {"elite_count": elite_count, "mutation_rate": effective_rate,
                    "mutation_strength": effective_strength, "immigrants": immigrant_count}


def neural_action(genome, inputs, hidden_size=8):
    """NumPy reference for auditing the identical Numba MLP in simulation."""
    inputs = np.asarray(inputs)
    cut = len(inputs) * hidden_size
    hidden = np.tanh(inputs @ genome[:cut].reshape(len(inputs), hidden_size) + genome[cut:cut + hidden_size])
    return np.tanh(hidden @ genome[cut + hidden_size:-2].reshape(hidden_size, 2) + genome[-2:])
