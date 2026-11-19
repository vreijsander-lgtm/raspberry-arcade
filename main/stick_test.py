"""Arcade stick tester.

Run on the Pi (stop the game first):  python3 stick_test.py
Move the stick and press the buttons. Every input is shown on screen and
printed in the terminal, so you can see which kind of connection works:

  GPIO      wires go straight to the Pi's pins (what the game uses now)
  KEY       the stick's USB board pretends to be a keyboard (game works
            only if the key is one the game knows: arrows, Space, Esc...)
  JOYSTICK  the USB board is a gamepad (stick = directions, button numbers
            for BUTTON1 / BUTTON2 are set in config.json "joy_buttons")

Close with Esc held for 2 seconds, or Alt+F4.
"""
import time

import pygame

from main import KEYMAP, Input, load_config

pygame.init()
screen = pygame.display.set_mode((800, 600))
pygame.display.set_caption("Stick test")
font = pygame.font.Font(None, 34)
small = pygame.font.Font(None, 26)

cfg = load_config()
inp = Input(cfg)              # sets up the GPIO pins from config.json
gpio_count = len(inp._buttons)

pygame.joystick.init()
sticks = [pygame.joystick.Joystick(i) for i in range(pygame.joystick.get_count())]
for js in sticks:
    js.init()

lines = []


def log(text):
    print(text)
    lines.append(text)
    del lines[:-14]


log("GPIO buttons set up: %d (pins from config.json)" % gpio_count)
log("USB gamepads found: %d %s" % (len(sticks), [js.get_name() for js in sticks]))

clock = pygame.time.Clock()
esc_since = None
running = True
while running:
    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False
        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_F4 and event.mod & pygame.KMOD_ALT:
                running = False
            if event.key == pygame.K_ESCAPE:
                esc_since = time.time()
            action = KEYMAP.get(event.key)
            log("KEY  %-10s -> %s" % (pygame.key.name(event.key),
                                     action.upper() if action else "not used by the game"))
        elif event.type == pygame.KEYUP and event.key == pygame.K_ESCAPE:
            esc_since = None
        elif event.type == pygame.JOYBUTTONDOWN:
            action = inp.joy_map.get(event.button)
            log("JOYSTICK  button %d -> %s" % (event.button,
                action.upper() if action else "not used (add it in config.json)"))
        elif event.type == pygame.JOYHATMOTION and event.value != (0, 0):
            log("JOYSTICK  hat %s" % (event.value,))
        elif event.type == pygame.JOYAXISMOTION and abs(event.value) > 0.5:
            names = {0: ("LEFT", "RIGHT"), 1: ("UP", "DOWN")}
            d = names.get(event.axis, ("-", "+"))[event.value > 0]
            log("JOYSTICK  axis %d -> %s" % (event.axis, d))
        elif event.type == pygame.JOYDEVICEADDED:
            js = pygame.joystick.Joystick(event.device_index)
            js.init()
            sticks.append(js)
            log("USB gamepad plugged in: %s" % js.get_name())

    # GPIO presses arrive through the Input queue
    while not inp.q.empty():
        kind, name = inp.q.get_nowait()
        if kind == "press":
            log("GPIO  pin %s -> %s" % (cfg["gpio_pins"][name], name.upper()))

    if esc_since and time.time() - esc_since > 2:
        running = False

    screen.fill((10, 10, 30))
    screen.blit(font.render("STICK TEST - move the stick, press buttons", True,
                            (255, 220, 80)), (20, 15))
    screen.blit(small.render("Hold Esc 2 s or Alt+F4 to close", True,
                             (150, 150, 190)), (20, 50))
    for i, text in enumerate(lines):
        screen.blit(small.render(text, True, (220, 230, 255)), (20, 95 + i * 34))
    pygame.display.flip()
    clock.tick(60)

pygame.quit()
