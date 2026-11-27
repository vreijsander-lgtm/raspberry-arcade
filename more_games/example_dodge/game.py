"""
DODGE - an example game. Copy this whole folder to start your own!

The arcade finds this file by itself: any folder in more_games/ with a
game.py in it shows up under MORE GAMES on the start screen.
"""
import random

import pygame

# --- shown in the arcade's list (keep these lines simple: NAME = "text") ---
TITLE = "DODGE"
AUTHOR = "THE ARCADE"
DESCRIPTION = "DODGE THE FALLING BLOCKS"
SCORE_NAME = "POINTS"

W, H = 540, 960          # the screen is tall: 540 wide, 960 high


class Game:
    def __init__(self):
        """A new round starts. Set everything up here."""
        self.score = 0           # the arcade reads this for the high scores
        self.game_over = False   # set to True when the round is over
        self.x = W / 2           # the player
        self.blocks = []         # falling blocks: [x, y, size, speed]
        self.timer = 0.0
        self.font = pygame.font.Font(None, 48)

    def update(self, dt, pressed, held):
        """Called 60 times a second.
        dt      = seconds since last time (about 0.016)
        pressed = buttons pressed JUST NOW, e.g. {"button2"}
        held    = buttons held down right now, e.g. {"left"}
        Buttons: "up", "down", "left", "right", "button2"
        (button1 is taken by the arcade: it opens the pause menu)"""
        speed = 420
        if "left" in held:
            self.x -= speed * dt
        if "right" in held:
            self.x += speed * dt
        self.x = max(25, min(W - 25, self.x))

        # a new block now and then - faster as your score goes up
        self.timer -= dt
        if self.timer <= 0:
            self.timer = max(0.15, 0.7 - self.score / 200)
            size = random.randint(30, 70)
            self.blocks.append([random.randint(0, W - size), -size, size,
                                random.randint(250, 400) + self.score * 3])

        player = pygame.Rect(self.x - 25, H - 120, 50, 50)
        for b in self.blocks:
            b[1] += b[3] * dt
            if player.colliderect(pygame.Rect(b[0], b[1], b[2], b[2])):
                self.game_over = True
        # blocks that fell off the bottom: one point each
        before = len(self.blocks)
        self.blocks = [b for b in self.blocks if b[1] < H]
        self.score += before - len(self.blocks)

    def draw(self, screen):
        """Draw everything on screen (a pygame Surface of 540 x 960).
        No need to update the display yourself - the arcade does that."""
        screen.fill((10, 10, 30))
        for b in self.blocks:
            pygame.draw.rect(screen, (255, 80, 120), (b[0], b[1], b[2], b[2]), border_radius=6)
        pygame.draw.rect(screen, (80, 220, 255), (self.x - 25, H - 120, 50, 50), border_radius=10)
        img = self.font.render("SCORE %d" % self.score, True, (255, 220, 80))
        screen.blit(img, (20, 20))
