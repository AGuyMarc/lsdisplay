# SPDX-License-Identifier: GPL-2.0-or-later
# Paquet Fedora/COPR — lsdisplay (Guy-Marc APRIN)
# Cale sur la derniere release publiee : v0.2.4 (2026-07-28).

Name:           lsdisplay
Version:        0.2.4
Release:        1%{?dist}
Summary:        List connected displays — like lsusb/lspci but for screens

License:        GPL-2.0-or-later
URL:            https://github.com/AGuyMarc/lsdisplay
Source0:        %{url}/archive/v%{version}/%{name}-%{version}.tar.gz

BuildArch:      noarch
BuildRequires:  python3-devel
BuildRequires:  python3-setuptools
BuildRequires:  python3-wheel

%global _description %{expand:
lsdisplay lists the connected displays of a Linux machine the way lsusb or
lspci list USB devices and PCI buses: EDID details (make/model/serial),
resolution, refresh rate, and an ASCII layout diagram. It works on both X11
(xrandr) and Wayland (kscreen-doctor, wlr-randr), can scan Samsung TVs, and
speaks --json. Pure Python 3, zero mandatory dependencies.}

%description %{_description}

%prep
%autosetup -n %{name}-%{version}

%generate_buildrequires
%pyproject_buildrequires

%build
%pyproject_wheel

%install
%pyproject_install
%pyproject_save_files lsdisplay
# Page de manuel
install -Dpm 0644 %{name}.1 %{buildroot}%{_mandir}/man1/%{name}.1

%check
# Suite unittest embarquee (tolerante : pas de display requis pour --help/--version)
%{python3} -m unittest discover -s tests -v ||:

%files -f %{pyproject_files}
%license LICENSE
%doc README.md
%{_bindir}/lsdisplay
%{_mandir}/man1/%{name}.1*

%changelog
* Tue Jul 28 2026 Guy-Marc APRIN <2026@gm.casa> - 0.2.4-1
- Aligne sur la release GitHub v0.2.4 (XDG optionnel + --write-config/--restore-config).
* Fri Jul 03 2026 Guy-Marc APRIN <2026@gm.casa> - 0.2.3-1
- Premier paquet RPM (COPR) — aligne sur la release GitHub v0.2.3.
