# Le problème #

On a `lsusb`, `lspci`, `lscpu`… mais rien pour les écrans ou les GPUs.
Pour savoir quel écran est branché sur quelle sortie, c'est la danse du
`xrandr | grep connected`, `cat /sys/class/drm/card*/edid | edid-decode`,
`nvidia-smi`… J'ai écrit deux outils pour régler ça.

## lsdisplay ##

Liste les écrans connectés avec fabricant, modèle, numéro de série,
résolution, fréquence, diagonale, et dessine un schéma ASCII du layout :

```text
$ lsdisplay

CONNECTED DISPLAYS
==================

  DP-4         1440x2560+0+0           27"  75Hz  Iiyama PL2792Q    DisplayPort  S/N:1152031921274   rot=left [PRIMARY]
  HDMI-A-2     1440x2560+1441+0        27"  75Hz  Iiyama PL2792Q    HDMI         S/N:1152032422031   rot=left
  HDMI-A-5     5376x3024+0+2561        65"  60Hz  Samsung QN800D    HDMI         S/N:94:e6:ba:dd:9a:7a

Total: 3 display(s) connected

LAYOUT
======

  +--------------+ +--------------+
  |              | |              |
  |     DP-4*    | |   HDMI-A-2   |
  |              | |              |
  +--------------+ +--------------+

  +------------------------------+
  |                              |
  |          HDMI-A-5            |
  |                              |
  +------------------------------+
```

Fonctionnalités :

* Parse les EDID directement depuis `/sys/class/drm` (pas de dépendance externe)
* Fonctionne sur X11 et Wayland (KDE, Sway, wlroots)
* Mode `--json` pour le scripting
* Mode `--scan` pour découvrir les Smart TV Samsung sur le réseau
* Fichier d'overrides pour corriger les EDID buggés (Samsung, je te regarde…)
* Python 3.6+, zéro dépendance

## lsgpu ##

Liste les GPUs avec stats NVIDIA, mapping écran par sortie :

```text
$ lsgpu

GRAPHICS CARDS
==============

  card0: NVIDIA GA107 [GeForce RTX 3050 6GB]
         Driver: nvidia | VRAM: 6 GB | GPU:0% MEM:2077/6144MB 37°C 16.7W
    ├─ DP-4: connected ← Iiyama PL2792Q 27"
    ├─ HDMI-A-2: connected ← Iiyama PL2792Q 27"

  card1: NVIDIA AD106 [GeForce RTX 4060 Ti]
         Driver: nvidia | VRAM: 16 GB | GPU:0% MEM:277/16380MB 41°C 14.9W
    ├─ HDMI-A-1: connected ← Samsung QE32Q50A 32"

  card2: Intel Arrow Lake-S [Intel Graphics]
         Driver: i915
    ├─ HDMI-A-5: connected ← Samsung TQ65QN800DTXXC 65"

Total: 3 GPU(s), 6 output(s) connected
```

Fonctionnalités :

* Stats NVIDIA (utilisation, température, puissance, mémoire)
* Stats AMD via sysfs
* Mode `--watch` avec sparklines en temps réel
* Liste des processus utilisant le GPU
* Python 3.6+, zéro dépendance Python

## Installation ##

```bash
sudo cp lsdisplay.py /usr/local/bin/lsdisplay
sudo chmod +x /usr/local/bin/lsdisplay
```

Paquet `.deb` disponible aussi. Un seul fichier Python, pas de pip, pas de venv.

## Appel à testeurs ##

C'est une v0.1.0 — testé sur ma config (multi-GPU NVIDIA + Intel, KDE Wayland,
6 écrans dont 2 Samsung TV). J'aimerais des retours sur :

* Configs AMD (j'ai le code mais pas le matos pour tester)
* Wayland hors KDE (Sway, GNOME, Hyprland)
* Écrans avec EDID exotiques
* Suggestions d'affichage ou de fonctionnalités

## Liens ##

* [lsdisplay sur GitHub](https://github.com/AGuyMarc/lsdisplay)
* [lsgpu sur GitHub](https://github.com/AGuyMarc/lsgpu)

Licence : GPL-2.0
