Name:       harbour-felisradio1
Summary:    Radio 1 live player for Sailfish OS
Version:    0.1.0
Release:    22
Group:      Qt/Qt
License:    GPL-3.0-or-later
Source0:    %{name}-%{version}.tar.bz2
Requires:   amber-qml-plugin-mpris
Requires:   sailfishsilica-qt5
Requires:   pyotherside-qml-plugin-python3-qt5
Requires:   qt5-qtdeclarative-import-multimedia
Requires:   python3-base >= 3.11
Requires:   python3-libs >= 3.11
BuildRequires: pkgconfig(sailfishapp) >= 1.0.2
BuildRequires: pkgconfig(Qt5Core)
BuildRequires: pkgconfig(Qt5Qml)
BuildRequires: pkgconfig(Qt5Quick)
BuildRequires: python3-base
BuildRequires: desktop-file-utils
BuildRequires: qt5-qttools-linguist
%global __requires_exclude_from ^%{_datadir}/%{name}/(python|vendor/python)/.*$
%global __provides_exclude_from ^%{_datadir}/%{name}/(python|vendor/python)/.*$

%description
Native single-station live radio player with Cast output, ICY metadata,
cover actions and MPRIS. For Jolla Phone 2026, with English and Czech user interfaces.

%prep
%setup -q -n %{name}-%{version}

%build
%qmake5 FELISRADIO1_VERSION=%{version}-%{release}
%make_build

%install
%qmake5_install
install -d -m 0755 %{buildroot}%{_datadir}/%{name}/translations
lrelease -nounfinished translations/%{name}-cs.ts -qm %{buildroot}%{_datadir}/%{name}/translations/%{name}-cs.qm
python3 tools/install_vendor.py vendor/runtime.zip %{buildroot}%{_datadir}/%{name}/vendor
desktop-file-install --delete-original --dir %{buildroot}%{_datadir}/applications %{buildroot}%{_datadir}/applications/*.desktop

%files
%license LICENSE COPYRIGHT
%doc README.md README.en.md THIRD_PARTY.md
%{_bindir}/%{name}
%{_datadir}/%{name}
%{_datadir}/applications/%{name}.desktop
%{_datadir}/icons/hicolor/*/apps/%{name}.png
