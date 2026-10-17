import math
import numpy as np
import pytest
from evolution_lab.config import SimulationConfig
from evolution_lab.core.evolution import initial_population, next_generation, neural_action, genome_size
from evolution_lab.core.simulation import (raycast, bicycle_step, swept_disc_collision,
    advance_checkpoints, simulate_generation, neural_action_compiled, CAR_RADIUS)
from evolution_lab.core.tracks import Track, generate_track, validate_track


def test_rays_use_first_actual_wall_and_range():
    walls = np.array([[5., -10, 5, 10], [9., -10, 9, 10]])
    assert raycast(0., 0., 0., walls, 50.) == 5
    assert raycast(0., 0., math.pi, walls, 50.) == 50
    assert raycast(0., 0., 0., walls, 3.) == 3


def test_physics_acceleration_braking_turning():
    straight = bicycle_step(0., 0., 0., 4., 0., 0., 1., .1, 22.)
    turned = bicycle_step(0., 0., 0., 4., 0., 1., 1., .1, 22.)
    braking = bicycle_step(0., 0., 0., 4., 0., 0., -1., .1, 22.)
    assert straight[0] > .4 and straight[1] == 0 and straight[3] > 4
    assert turned[2] > 0 and turned[1] > 0
    assert 0 <= braking[3] < 4
    assert CAR_RADIUS >= math.hypot(3.6 / 2, 1.7 / 2)


def test_swept_disc_detects_grazing_between_valid_endpoints():
    wall = np.array([[0., 0., 0., 1.]])
    # Endpoints are sqrt(2) from wall, midpoint only1 away.
    assert swept_disc_collision(-1., 2., 1., 2., wall, 1.1)
    assert not swept_disc_collision(-1., 3., 1., 3., wall, 1.1)
    assert swept_disc_collision(-5., .5, 5., .5, wall, .1)


def test_checkpoints_order_reverse_and_shortcut_rejection():
    track = Track("test", 12., False, [[0, 0], [10, 0], [20, 0], [30, 0]])
    def advance(old, new, passed=0):
        return advance_checkpoints(*old, *new, passed, track.starts, track.ends, track.tangents,
                                   track.segment_lengths, track.cumulative, track.width)
    assert advance((9., 0.), (11., 0.))[0] == 1
    assert advance((11., 0.), (9., 0.))[0] == 0
    assert advance((9., 20.), (11., 20.))[0] == 0
    # Being near later checkpoints without crossing the first gives no credit.
    passed, progress = advance((21., 0.), (22., 0.))
    assert passed == 0 and progress < .37
    for _ in range(10):
        passed, progress = advance((11., 0.), (9., 0.), passed)
    assert passed == 0 and progress < .37


def test_mlp_matches_reference_without_privileged_track_inputs():
    config = SimulationConfig(population=4)
    population = initial_population(config, np.random.default_rng(9))
    inputs = np.linspace(.1, .8, config.sensors + 1)
    assert population.shape == (4, genome_size(7, 8))
    np.testing.assert_allclose(neural_action_compiled(population[0], inputs, 8),
                               neural_action(population[0], inputs, 8), rtol=1e-6, atol=1e-7)


def test_genetics_elites_variation_and_reproducibility():
    config = SimulationConfig(population=40, elite_fraction=.1)
    population = initial_population(config, np.random.default_rng(10))
    scores = np.arange(40.)
    first, data = next_generation(population, scores, config, np.random.default_rng(11), stagnation=20)
    second, _ = next_generation(population, scores, config, np.random.default_rng(11), stagnation=20)
    np.testing.assert_array_equal(first, second)
    np.testing.assert_array_equal(first[:4], population[[39, 38, 37, 36]])
    assert not np.array_equal(first[4:], population[4:])
    assert data["mutation_strength"] > config.mutation_strength
    assert np.isfinite(first).all()


@pytest.mark.parametrize("name,difficulty,closed", [
    ("oval", "easy", True), ("kidney", "medium", True),
    ("technical", "hard", True), ("chicane", "extreme", True),
    ("procedural", "easy", True), ("procedural", "extreme", False)])
def test_tracks_are_geometrically_valid_and_drivable(name, difficulty, closed):
    track = generate_track(name, seed=71, difficulty=difficulty, closed=closed)
    assert track.validation["valid"]
    assert track.validation["reference"]["completed"]
    assert track.length > 600
    assert track.validation["reference"]["max_lateral_error"] + CAR_RADIUS < track.width / 2


def test_procedural_seeds_are_reproducible_and_different():
    first = generate_track("procedural", seed=11)
    second = generate_track("procedural", seed=11)
    other = generate_track("procedural", seed=12)
    np.testing.assert_array_equal(first.centerline, second.centerline)
    assert not np.array_equal(first.centerline, other.centerline)


def test_named_technical_and_chicane_tracks_are_distinct():
    technical = generate_track("technical", difficulty="medium")
    chicane = generate_track("chicane", difficulty="medium")
    assert not np.array_equal(technical.centerline, chicane.centerline)


def test_invalid_self_intersection_rejected():
    track = Track("invalid", 10., True, [[0, 0], [80, 80], [0, 80], [80, 0]])
    assert not validate_track(track)["valid"]


def test_simulation_timeout_replay_integrity_and_reproducibility():
    config = SimulationConfig(population=24, max_seconds=3.)
    track = generate_track()
    brains = initial_population(config, np.random.default_rng(config.seed))
    a = simulate_generation(track, brains, config, generation=7)
    b = simulate_generation(track, brains, config, generation=7)
    np.testing.assert_array_equal(a.scores, b.scores)
    np.testing.assert_array_equal(a.replay["positions"], b.replay["positions"])
    assert a.replay["positions"].shape[1] == 24
    assert int(a.replay["generation"]) == 7
    assert a.replay["times"][-1] <= 3.
    assert np.all(np.diff(a.replay["progress"], axis=0) >= 0)
    assert np.all((0 <= a.progress) & (a.progress <= 1))
    assert np.isfinite(a.scores).all()
    assert np.all(np.diff(a.replay["alive"].astype(int), axis=0) <= 0)
    for index in range(config.population):
        inactive = np.where(~a.replay["alive"][:, index])[0]
        if len(inactive):
            p = a.replay["positions"][inactive[0]:, index]
            assert np.all(p == p[0])


def test_open_track_finish_does_not_hit_end_cap():
    config = SimulationConfig(population=2, max_seconds=20., closed=False)
    track = Track("straight", 12., False, [[0, 0], [20, 0], [40, 0], [60, 0]])
    brains = np.zeros((2, genome_size(config.sensors, config.hidden_size)), np.float32)
    brains[:, -1] = 3.  # Test-only straight accelerator, not used in training.
    evaluation = simulate_generation(track, brains, config)
    assert evaluation.completed.all()
    assert np.all(evaluation.replay["positions"][-1, :, 0] < 60 - CAR_RADIUS)


@pytest.mark.parametrize("kwargs", [dict(sensors=4), dict(population=0), dict(dt=float("nan")),
                                    dict(seed=-1), dict(track="invented"),
                                    dict(population=10000, max_seconds=600, replay_fps=30)])
def test_configuration_rejects_invalid_and_unsafe_allocations(kwargs):
    with pytest.raises(ValueError):
        SimulationConfig(**kwargs)
