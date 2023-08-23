#
# File: pgbackman.spec
#
# Autor: Rafael Martinez <rafael@postgreslq.org.es>
#  

%define majorversion 1.3
%define minorversion 1
%define pbm_owner pgbackman
%define pbm_group pgbackman
%define __python /usr/bin/python2
%{!?pybasever: %define pybasever %(python2 -c "import sys;print(sys.version[0:3])")}
%{!?python_sitelib: %define python_sitelib %(python2 -c "from distutils.sysconfig import get_python_lib; print get_python_lib()")}

Summary:        PostgreSQL backup manager
Name:           pgbackman
Version:        %{majorversion}.%{minorversion}
Release:        1%{?dist}
License:        GPLv3
Group:          Applications/Databases
Url:            http://www.pgbackman.org/
Source0:        %{name}-%{version}.tar.gz
BuildRoot:      %{_tmppath}/%{name}-%{version}-%{release}-buildroot-%(%{__id_u} -n)
BuildArch:      noarch
Requires:       python2-psycopg2 >= 2.4.0, at, cronie, python2-setuptools, shadow-utils, logrotate

%description 
PgBackMan is a tool for managing PostgreSQL logical backups created
with pg_dump and pg_dumpall.

It is designed to manage backups from thousands of databases running
in multiple PostgreSQL nodes, and it supports a multiple backup
servers topology.

It also manages role and database configuration information when
creating a backup of a database. This information is necessary to
ensure a 100% restore of a logical backup of a database and the
elements associated to it.

%prep
%setup -n %{name}-%{version} -q

%build
python2 setup.py build

%install
python2 setup.py install -O1 --skip-build --root %{buildroot}
mkdir -p %{buildroot}/var/lib/%{name}
mkdir -p %{buildroot}/var/log/%{name}
touch %{buildroot}/var/log/%{name}/%{name}.log

%clean
rm -rf %{buildroot}

%files
%defattr(-,root,root)
%doc INSTALL
%{python_sitelib}/%{name}-%{version}-py%{pybasever}.egg-info/
%{python_sitelib}/%{name}/
%{_bindir}/%{name}*
%{_sysconfdir}/init.d/%{name}*
%{_sysconfdir}/logrotate.d/%{name}*
%{_datadir}/%{name}/*
/var/log/%{name}/*
%config(noreplace) %{_sysconfdir}/%{name}/%{name}.conf
%config(noreplace) %{_sysconfdir}/%{name}/%{name}_alerts.template
%attr(700,%{pbm_owner},%{pbm_group}) %dir /var/lib/%{name}
%attr(755,%{pbm_owner},%{pbm_group}) %dir /var/log/%{name}
%attr(600,%{pbm_owner},%{pbm_group}) %ghost /var/log/%{name}/%{name}.log

%pre
groupadd -f -r pgbackman >/dev/null 2>&1 || :
useradd -M -N -g pgbackman -r -d /var/lib/pgbackman -s /bin/bash \
        -c "PostgreSQL Backup Manager" pgbackman >/dev/null 2>&1 || :

%changelog
* Wed May 25 2023 - James Miller <jvaskonen@toastaddict.org> 1.3.1-1
- New release 1.3.1

* Tue Jun 13 2017 - Rafael Martinez Guerrero <rafael@postgresql.org.es> 1.2.0-1
- New release 1.0.0

* Mon Jun 24 2014 - Rafael Martinez Guerrero <rafael@postgresql.org.es> 1.0.0-1
- New release 1.0.0
