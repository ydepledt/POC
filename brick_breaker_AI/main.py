import pygame
import numpy as np
import sys

# Initialiser Pygame
pygame.init()

# Dimensions de la fenêtre
width, height = 600, 400
screen = pygame.display.set_mode((width, height))
pygame.display.set_caption("Pendule inversé avec Contrôle Manuel")

# Définir la fréquence de rafraîchissement
clock = pygame.time.Clock()
fps = 60

# Paramètres physiques du système
cart_width, cart_height = 50, 30
pole_length = 20

# Position initiale
cart_x = width // 2
cart_y = height - cart_height - 50

# Angle initial du pendule (vertical)
theta = np.pi  # Pendule à 180° (droit vers le bas)

# Paramètres physiques simplifiés
gravity = 9.8
mass_pole = 100
mass_cart = 10.0
force_mag = 1000.0
dt = 1 / fps

# Variables de vitesse initiale
cart_velocity = 0
pole_angular_velocity = 0

# Fonction pour dessiner le chariot et le pendule
def draw_cart_pole(cart_x, theta):
    # Dessiner le chariot
    pygame.draw.rect(screen, (0, 0, 255), (cart_x - cart_width // 2, cart_y, cart_width, cart_height))
    
    # Calculer la position de l'extrémité du pendule
    pole_x = cart_x + pole_length * np.sin(theta)
    pole_y = cart_y - pole_length * np.cos(theta)
    
    # Dessiner le pendule
    pygame.draw.line(screen, (255, 0, 0), (cart_x, cart_y), (pole_x, pole_y), 5)
    
    # Dessiner le point d'attache
    pygame.draw.circle(screen, (0, 0, 0), (int(cart_x), int(cart_y)), 5)

    # Dessiner le point final du pendule
    pygame.draw.circle(screen, (0, 0, 0), (int(pole_x), int(pole_y)), 10)

# Fonction pour mettre à jour la physique du système
def update_physics(force, cart_x, theta, theta_dot, cart_velocity):
    # Calcul des sin et cos de l'angle
    sin_theta = np.sin(theta)
    cos_theta = np.cos(theta)
    
    # Calcul temporaire pour simplifier les équations
    temp = (force + mass_pole * pole_length * theta_dot**2 * sin_theta) / (mass_cart + mass_pole)
    
    # Accélération angulaire du pendule
    theta_ddot = (gravity * sin_theta - cos_theta * temp) / (pole_length * (4.0/3.0 - (mass_pole * cos_theta**2) / (mass_cart + mass_pole)))
    
    # Mise à jour de la vitesse angulaire et de l'angle
    theta_dot += theta_ddot * dt
    theta += theta_dot * dt
    
    # Mise à jour de l'accélération du chariot en tenant compte de l'accélération angulaire du pendule
    cart_acceleration = (force + mass_pole * pole_length * (theta_dot**2 * sin_theta - theta_ddot * cos_theta)) / (mass_cart + mass_pole)
    cart_velocity += cart_acceleration * dt
    cart_x += cart_velocity * dt
    
    return cart_x, theta, theta_dot, cart_velocity

# Boucle principale du jeu
def main():
    global cart_x, theta, pole_angular_velocity, cart_velocity
    running = True
    control_mode = 'manual'  # Modes possibles : 'manual' ou 'agent'
    
    while running:
        screen.fill((255, 255, 255))
        
        # Variables pour la force appliquée
        force = 0
        
        # Gestion des événements
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
                pygame.quit()
                sys.exit()
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_m:
                    control_mode = 'manual'
                elif event.key == pygame.K_a:
                    control_mode = 'agent'
        
        if control_mode == 'manual':
            # Gestion des entrées clavier pour le mode manuel
            keys = pygame.key.get_pressed()
            if keys[pygame.K_LEFT]:
                force -= force_mag  # Appliquer une force vers la gauche
            if keys[pygame.K_RIGHT]:
                force += force_mag  # Appliquer une force vers la droite
        elif control_mode == 'agent':
            # Ici, tu intégrerais l'action choisie par l'agent RL
            # Par exemple :
            # force = agent.get_action(state)
            pass  # Remplacer par l'appel à l'agent RL
        
        # Optionnel : Limiter la force pour éviter des comportements trop brusques
        force = np.clip(force, -force_mag, force_mag)
        
        # Mettre à jour la physique avec la force appliquée
        cart_x, theta, pole_angular_velocity, cart_velocity = update_physics(
            force, cart_x, theta, pole_angular_velocity, cart_velocity
        )
        
        # Dessiner le chariot et le pendule
        draw_cart_pole(cart_x, theta)
        
        # Afficher des informations (optionnel)
        font = pygame.font.SysFont(None, 24)
        info_text = f"Mode: {control_mode} | Force appliquée: {force:.2f} N | Angle du pendule: {np.degrees(theta):.2f}°"
        img = font.render(info_text, True, (0, 0, 0))
        screen.blit(img, (20, 20))
        
        # Mettre à jour l'affichage
        pygame.display.flip()
        clock.tick(fps)
    
    pygame.quit()

if __name__ == "__main__":
    main()
