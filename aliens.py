import math
import random
from dataclasses import dataclass

import pygame

# GlitterTurret vs the Aliens — glittery arcade shooter.
# Controls:
#   Aim: mouse (recommended). Arrow Keys nudge aim angle.
#   Strafe: A/D to move the turret sideways.
#   Fire: Space = quick shots. Hold & release Left Mouse = charged powerful shot.
#   Restart: R (after Game Over)

WIDTH, HEIGHT = 3840, 2160
FPS = 60
RED = (255, 80, 120)
GREEN = (100, 255, 160)
BLUE = (90, 170, 255)
PURPLE = (200, 130, 255)
CYAN = (120, 240, 255)
MAGENTA = (255, 120, 240)
ORANGE = (255, 170, 80)
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
YELLOW = (255, 230, 90)
LIGHT_GREY = (200, 200, 220)
GREY = (18, 18, 28)

# Gameplay constants
GRAVITY = 0.18
TURRET_STRAFE_SPEED = 6.0


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def length2(dx, dy):
    return dx * dx + dy * dy


def angle_to(from_x, from_y, to_x, to_y):
    return math.atan2(to_y - from_y, to_x - from_x)


@dataclass
class Cannonball:
    x: float
    y: float
    vx: float
    vy: float
    r: int = 4
    color: tuple = (255, 255, 255)

    def update(self):
        self.vy += GRAVITY
        self.x += self.vx
        self.y += self.vy

    def offscreen(self):
        return (
            self.x < -20 or self.x > WIDTH + 20 or self.y < -20 or self.y > HEIGHT + 20
        )


@dataclass
class Alien:
    x: float
    y: float
    vx: float
    vy: float
    shoot_cd: float
    alive: bool = True
    radius: int = 16
    color: tuple = (180, 255, 120)

    def update(self, target_x, target_y, bullets):
        # Erratic movement: base sine wobble + gentle drift
        wobble = math.sin(pygame.time.get_ticks() * 0.005 + self.x * 0.05) * 0.8
        self.vx += wobble * 0.05

        # Evasive: steer away from nearest cannonball slightly
        nearest = None
        min_d2 = 1e9
        for b in bullets:
            d2 = length2(b.x - self.x, b.y - self.y)
            if d2 < min_d2:
                min_d2 = d2
                nearest = b
        if nearest and min_d2 < 180**2:
            dx = self.x - nearest.x
            dy = self.y - nearest.y
            d = math.hypot(dx, dy) + 1e-6
            self.vx += (dx / d) * 0.15
            self.vy += (dy / d) * 0.12

        # Main goal is to descend and pressure the player (slightly eased)
        self.vy += 0.015

        # Clamp speed
        spd = math.hypot(self.vx, self.vy)
        if spd > 3.6:
            self.vx *= 3.6 / spd
            self.vy *= 3.6 / spd

        self.x += self.vx
        self.y += self.vy

        # Edge bounce to keep in play
        if self.x < 20 or self.x > WIDTH - 20:
            self.vx *= -1
        self.x = clamp(self.x, 20, WIDTH - 20)

        # Shooting cooldown countdown
        if self.shoot_cd > 0:
            self.shoot_cd -= 1

    def want_shoot(self):
        return self.shoot_cd <= 0

    def reset_shoot(self):
        self.shoot_cd = random.randint(60, 140)


@dataclass
class AlienShot:
    x: float
    y: float
    vx: float
    vy: float
    color: tuple = (255, 120, 120)
    r: int = 4

    def update(self):
        self.x += self.vx
        self.y += self.vy

    def offscreen(self):
        return self.y > HEIGHT + 10 or self.x < -10 or self.x > WIDTH + 10


@dataclass
class Particle:
    x: float
    y: float
    angle: float
    speed: float
    vy: float
    life: int
    color: tuple
    blink: bool

    def update(self):
        # Movement based on angle as requested
        self.x += math.sin(self.angle) * self.speed
        self.y += math.cos(self.angle) * self.speed
        # Gravity pulls down
        self.vy += GRAVITY * 0.4
        self.y += self.vy
        # Fade life
        self.life -= 1


class ParticleSystem:
    def __init__(self, max_particles=30000):
        self.particles: list[Particle] = []
        self.max_particles = max_particles

    def spawn_explosion(self, x, y, count=1000):
        # Cap total particles to avoid perf issues
        available = max(0, self.max_particles - len(self.particles))
        n = min(count, available)
        for _ in range(n):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(0.5, 3.0)
            vy = random.uniform(-1.0, -0.2)
            life = random.randint(20, 50)
            # Sparkly colors with occasional bright white blink
            base_colors = [YELLOW, ORANGE, MAGENTA, CYAN, PURPLE, BLUE, GREEN, RED]
            color = random.choice(base_colors)
            blink = random.random() < 0.1
            self.particles.append(Particle(x, y, angle, speed, vy, life, color, blink))

    def update(self):
        alive = []
        for p in self.particles:
            p.update()
            if p.life > 0 and -5 < p.x < WIDTH + 5 and -5 < p.y < HEIGHT + 5:
                alive.append(p)
        self.particles = alive

    def draw(self, surf):
        # Draw as 1px sparkles
        for p in self.particles:
            if p.blink and (p.life % 6 < 2):
                color = WHITE
            else:
                color = p.color
            # set_at is fine for 1px particles; avoid blending cost
            if 0 <= int(p.x) < WIDTH and 0 <= int(p.y) < HEIGHT:
                surf.set_at((int(p.x), int(p.y)), color)


@dataclass
class Turret:
    x: float
    y: float
    angle: float = -math.pi / 2  # up
    cooldown: int = 0
    fire_rate: int = 8  # frames between shots when holding
    shield: int = 130

    def aim_at(self, tx, ty):
        self.angle = angle_to(self.x, self.y, tx, ty)

    def nudge(self, delta):
        self.angle += delta
        self.angle = clamp(self.angle, -math.pi + 0.2, -0.2)

    def move(self, dx):
        # Strafe horizontally with clamp to keep shield fully on screen
        self.x = clamp(self.x + dx, 40, WIDTH - 40)

    def update(self):
        if self.cooldown > 0:
            self.cooldown -= 1

    def can_fire(self):
        return self.cooldown == 0

    def fire(self, power=14.0):
        # Spawn a cannonball from turret tip
        tip_x = self.x + math.cos(self.angle) * 30
        tip_y = self.y + math.sin(self.angle) * 30
        vx = math.cos(self.angle) * power
        vy = math.sin(self.angle) * power
        self.cooldown = self.fire_rate
        col = random.choice([(255, 255, 255), YELLOW, CYAN, ORANGE])
        return Cannonball(tip_x, tip_y, vx, vy, r=5, color=col)

    def draw(self, surf):
        # Base
        pygame.draw.circle(surf, LIGHT_GREY, (int(self.x), int(self.y)), 18)
        # Barrel
        tip = (self.x + math.cos(self.angle) * 32, self.y + math.sin(self.angle) * 32)
        pygame.draw.line(surf, WHITE, (self.x, self.y), tip, 6)
        # Forcefield (shield)
        radius = 40
        alpha = clamp(int(80 + 120 * (self.shield / 100)), 40, 200)
        s = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        pygame.draw.circle(
            s, (120, 200, 255, alpha), (radius + 2, radius + 2), radius, 3
        )
        # faint rotating sparkle around shield
        t = pygame.time.get_ticks() * 0.005
        for k in range(6):
            a = t + k * math.tau / 6
            px = radius + 2 + math.cos(a) * radius
            py = radius + 2 + math.sin(a) * radius
            if 0 <= int(px) < s.get_width() and 0 <= int(py) < s.get_height():
                s.set_at((int(px), int(py)), (255, 255, 255, 200))
        surf.blit(s, (self.x - radius - 2, self.y - radius - 2))


def collide_circ(a_x, a_y, a_r, b_x, b_y, b_r):
    return length2(a_x - b_x, a_y - b_y) <= (a_r + b_r) ** 2


def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("Glitter Turret vs Aliens")
    clock = pygame.time.Clock()
    font = pygame.font.SysFont("consolas", 20)

    turret = Turret(WIDTH / 2, HEIGHT - 60)
    bullets: list[Cannonball] = []
    aliens: list[Alien] = []
    alien_shots: list[AlienShot] = []
    particles = ParticleSystem(max_particles=30000)

    spawn_timer = 0
    score = 0
    game_over = False

    # Charging shot state
    charging = False
    charge_time = 0  # frames
    CHARGE_TIME_MAX = 60  # ~1 second at 60 FPS

    running = True
    while running:
        _ = clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.KEYDOWN:
                if event.key == pygame.K_r and game_over:
                    # Reset game
                    turret = Turret(WIDTH / 2, HEIGHT - 60)
                    bullets.clear()
                    aliens.clear()
                    alien_shots.clear()
                    particles.particles.clear()
                    spawn_timer = 0
                    score = 0
                    game_over = False

        keys = pygame.key.get_pressed()
        mx, my = pygame.mouse.get_pos()

        # Aim with mouse primarily
        turret.aim_at(mx, my)
        # Keyboard nudge (aim) with Arrow keys only
        nudge = 0.0
        if keys[pygame.K_LEFT]:
            nudge -= 0.04
        if keys[pygame.K_RIGHT]:
            nudge += 0.04
        turret.nudge(nudge)

        # Strafe with A/D
        if keys[pygame.K_a]:
            turret.move(-TURRET_STRAFE_SPEED)
        if keys[pygame.K_d]:
            turret.move(TURRET_STRAFE_SPEED)

        # Fire controls
        mouse_left = pygame.mouse.get_pressed()[0]
        space_pressed = keys[pygame.K_SPACE]
        turret.update()

        # Quick fire with Space (disabled while charging a mouse shot)
        if not game_over and not charging and space_pressed and turret.can_fire():
            bullets.append(turret.fire())

        # Charge shot with Left Mouse
        if not game_over:
            if mouse_left:
                if not charging:
                    charging = True
                    charge_time = 0
                else:
                    charge_time = min(charge_time + 1, CHARGE_TIME_MAX)
            else:
                if charging:
                    # Release -> fire a single powerful shot
                    frac = charge_time / CHARGE_TIME_MAX
                    power = 14.0 + 10.0 * frac  # up to ~24 power
                    shot = turret.fire(power=power)
                    # Make charged shots bigger and brighter
                    shot.r = 5 + int(5 * frac)
                    if frac < 0.33:
                        shot.color = YELLOW
                    elif frac < 0.66:
                        shot.color = ORANGE
                    else:
                        shot.color = MAGENTA
                    bullets.append(shot)
                    charging = False
                    charge_time = 0

        # Spawn aliens
        if not game_over:
            if spawn_timer <= 0:
                # Spawn a small group (slightly easier pacing)
                for _ in range(random.randint(1, 2)):
                    x = random.randint(60, WIDTH - 60)
                    y = random.randint(-120, -20)
                    vx = random.uniform(-1.0, 1.0)
                    vy = random.uniform(0.15, 0.8)
                    cd = random.randint(50, 140)
                    aliens.append(Alien(x, y, vx, vy, cd))
                # Reduce spawn intensity by ~15% by lengthening interval
                spawn_timer = random.randint(58, 104)
            else:
                spawn_timer -= 1

        # Updates
        for b in bullets:
            b.update()
        bullets = [b for b in bullets if not b.offscreen()]

        for a in aliens:
            a.update(turret.x, turret.y, bullets)
            if a.want_shoot():
                ang = angle_to(a.x, a.y, turret.x, turret.y)
                sp = random.uniform(2.6, 3.6)
                alien_shots.append(
                    AlienShot(
                        a.x, a.y, math.cos(ang) * sp, math.sin(ang) * sp, color=RED
                    )
                )
                a.reset_shoot()

        # Collisions: cannonballs with aliens
        for a in aliens:
            if not a.alive:
                continue
            for b in bullets:
                if collide_circ(a.x, a.y, a.radius, b.x, b.y, b.r):
                    a.alive = False
                    particles.spawn_explosion(a.x, a.y, count=1000)
                    score += 10
                    break

        aliens = [a for a in aliens if a.alive and a.y < HEIGHT + 40]

        # Alien shots update
        for s in alien_shots:
            s.update()
        alien_shots = [s for s in alien_shots if not s.offscreen()]

        # --- Shield recharge logic ---
        # Config
        SHIELD_MAX = 130
        SHIELD_RECHARGE_DELAY = 120  # frames (~2s)
        SHIELD_RECHARGE_RATE = 4.0 / FPS  # HP per frame (~4 HP/sec)
        if not hasattr(main, "_shield_cd"):
            main._shield_cd = 0
            main._shield_accum = 0.0

        # Alien shots vs shield
        if not game_over:
            for s in alien_shots:
                if collide_circ(turret.x, turret.y, 40, s.x, s.y, s.r):
                    particles.spawn_explosion(s.x, s.y, count=120)
                    turret.shield -= 5
                    # Reset recharge cooldown on taking damage
                    main._shield_cd = SHIELD_RECHARGE_DELAY
                    s.y = HEIGHT + 100  # mark for removal
            alien_shots = [s for s in alien_shots if s.y < HEIGHT + 50]

        # Apply shield recharge when not recently damaged
        if not game_over:
            if main._shield_cd > 0:
                main._shield_cd -= 1
            else:
                if turret.shield < SHIELD_MAX:
                    main._shield_accum += SHIELD_RECHARGE_RATE
                    while main._shield_accum >= 1.0 and turret.shield < SHIELD_MAX:
                        turret.shield += 1
                        main._shield_accum -= 1.0

        # Aliens too close -> assimilation (game over)
        if not game_over:
            for a in aliens:
                if collide_circ(turret.x, turret.y, 28, a.x, a.y, a.radius):
                    particles.spawn_explosion(turret.x, turret.y, count=1500)
                    game_over = True
                    break

        if not game_over and turret.shield <= 0:
            game_over = True

        particles.update()

        # RENDER
        screen.fill(GREY)
        # Starry glittery background
        t = pygame.time.get_ticks() * 0.002
        for i in range(60):
            px = (i * 131) % WIDTH
            py = int((math.sin(t + i * 0.27) * 0.5 + 0.5) * HEIGHT)
            c = (200 + (i * 3) % 55, 200 + (i * 5) % 55, 220 + (i * 7) % 35)
            if 0 <= px < WIDTH and 0 <= py < HEIGHT:
                screen.set_at((px, py), c)

        # Draw aliens
        for a in aliens:
            pygame.draw.circle(screen, a.color, (int(a.x), int(a.y)), a.radius)
            eye = (int(a.x + math.sin(t + a.x * 0.02) * 6), int(a.y - 3))
            pygame.draw.circle(screen, BLACK, eye, 4)

        # Draw alien shots
        for s in alien_shots:
            pygame.draw.circle(screen, RED, (int(s.x), int(s.y)), s.r)

        # Draw turret and bullets
        turret.draw(screen)
        for b in bullets:
            pygame.draw.circle(screen, b.color, (int(b.x), int(b.y)), b.r)

        # Particles last to layer sparkles on top
        particles.draw(screen)

        # HUD
        info = (
            f"Score: {score}  Shield: {max(0, turret.shield)}  "
            f"Aim: Mouse/Arrows  Strafe: A/D  Fire: LMB(hold)+release / Space"
        )
        txt = font.render(info, True, WHITE)
        screen.blit(txt, (16, 14))

        # Charge bar UI at bottom center
        bar_w, bar_h = 180, 10
        bar_x = WIDTH // 2 - bar_w // 2
        bar_y = HEIGHT - 28
        pygame.draw.rect(screen, LIGHT_GREY, (bar_x, bar_y, bar_w, bar_h), 2)
        if charging or charge_time > 0:
            frac = (charge_time / CHARGE_TIME_MAX) if CHARGE_TIME_MAX else 0
            fill_w = int(bar_w * frac)
            color = YELLOW if frac < 0.33 else ORANGE if frac < 0.66 else MAGENTA
            pygame.draw.rect(
                screen, color, (bar_x + 1, bar_y + 1, max(0, fill_w - 2), bar_h - 2)
            )

        if game_over:
            over = font.render("Assimilated! Press R to Restart", True, ORANGE)
            screen.blit(over, (WIDTH / 2 - over.get_width() / 2, HEIGHT / 2 - 10))

        pygame.display.flip()

    pygame.quit()


if __name__ == "__main__":
    main()
