%global         debug_package   %{nil}
# elastic requires minimun version of java compiler is 15, we use jdk-11 for building
%global         build_java      java-11-openjdk
# maintain the consistency of the running env with others ELK components
%global         runtime_java    jre-11-openjdk
%global         distri_src      distribution/packages/src
%global         distri_common   %{distri_src}/common
%global         distri_systemd  %{distri_common}/systemd

%bcond_with     details

Name:           elasticsearch
Version:        7.9.0
Release:        1
Group:          Application/Internet
Summary:        Distributed RESTful search engine built for the cloud
License:        Elastic License
URL:            https://www.elastic.co/cn/%{name}
Source0:        https://github.com/elastic/%{name}/archive/refs/tags/v%{version}.tar.gz

Patch0:         fix-build.patch

BuildRequires:  %{build_java}-devel %{runtime_java} expect gcc-c++ cpio
# since this package automatically provides some required dependencies, disable automatic find dependencies
AutoReqProv:    no
Requires:       %{runtime_java} libstdc++ libgcc glibc zlib systemd coreutils


%description
Elasticsearch is a distributed, RESTful search and analytics engine capable of
addressing a growing number of use cases. As the heart of the Elastic Stack, it
centrally stores your data for lightning fast search, fine‑tuned relevancy, and
powerful analytics that scale with ease.

Reference documentation can be found at
https://www.elastic.co/guide/en/elasticsearch/reference/current/index.html
and the 'Elasticsearch: The Definitive Guide' book can be found at
https://www.elastic.co/guide/en/elasticsearch/guide/current/index.html


%prep
%autosetup -p1
# Do not directly use java in the system, it may be version 1.8.0
sed -ri '/JAVA_HOME=/cJAVA_HOME=%{_jvmlibdir}\/%{runtime_java}' %{distri_common}/env/%{name}


%build
export JAVA_HOME="%{_jvmlibdir}/%{build_java}"
export RUNTIME_JAVA_HOME="%{_jvmlibdir}/%{runtime_java}"
# for x86_64
export build_type="no-jdk"
# for arm64
%ifarch aarch64
export build_type="%{_arch}"
%endif
# it's not working that provides license.key from building parameter, 
# but we must provide this parameter to meet the verification condition
expect <<EOF
set timeout 7200
spawn ./gradlew distribution:packages:${build_type}-rpm:assemble \
    -Dbuild.snapshot=false -Dlicense.key="x-pack/plugin/core/snapshot.key" \
    %{?with_details:--stacktrace --debug --scan} %{!?with_details:--info}
expect {
    "Publishing a build scan to scans.gradle.com requires accepting the Gradle Terms*yes*no" { send "yes\r"; exp_continue}
}
EOF
# replace real version of elasticsearch in systemd unit file.
sed -i '/Built for/c# Built for packages-'%{version}' (packages)' %{distri_systemd}/%{name}.service


%install
# directory name is different from aarch64 and x86_64
%ifarch aarch64
dir_prefix="%{_arch}-"
%endif

target_file="distribution/packages/${dir_prefix}no-jdk-rpm/build/distributions/%{name}-%{version}-no-jdk-%{_arch}.rpm"
if test -f "${target_file}"; then
    rpm2cpio "${target_file}" | cpio -di -D %{buildroot}
else
    echo "cannot find target package." >&2
    exit 1
fi


%pre
case "$1" in
# 1 for install and 2 for upgrade
1 | 2)
    # Create elasticsearch group if not existing
    if ! getent group %{name} >/dev/null 2>&1; then
        echo -n "Creating %{name} group..."
        groupadd -r %{name}
        echo " OK"
    fi

    # Create elasticsearch user if not existing
    if ! id %{name} >/dev/null 2>&1; then
        echo -n "Creating %{name} user..."
        useradd --system \
            --no-create-home \
            --gid %{name} \
            --shell "$(command -v nologin)" \
            --comment "%{name} user" \
            %{name}
        echo " OK"
    fi
    ;;

*)
    echo "pre install script called with unknown argument \`$1'" >&2
    exit 1
    ;;
esac


%post
if test -f "%{_sysconfdir}/sysconfig/%{name}"; then
    source "%{_sysconfdir}/sysconfig/%{name}"
fi

IS_UPGRADE=false
# 1 for install and 2 for upgrade
case "$1" in
1)
    IS_UPGRADE=false
    ;;
2)
    IS_UPGRADE=true
    ;;
*)
    echo "post install script called with unknown argument \`$1'" >&2
    exit 1
    ;;
esac

systemctl restart systemd-sysctl.service || true

if test "x${IS_UPGRADE}" != "xtrue"; then
    echo "# NOT starting on installation, please execute the following statements to configure %{name} service to start automatically using systemd"
    echo " sudo systemctl daemon-reload"
    echo " sudo systemctl enable %{name}.service"
    echo "# You can start %{name} service by executing"
    echo " sudo systemctl start %{name}.service"
elif test "${RESTART_ON_UPGRADE}" = "true"; then
    echo -n "Restarting %{name} service..."
    systemctl daemon-reload
    systemctl restart %{name}.service || true
    echo " OK"
fi


%preun
if test -f "%{_sysconfdir}/sysconfig/%{name}"; then
    source "%{_sysconfdir}/sysconfig/%{name}"
fi
export ES_PATH_CONF=${ES_PATH_CONF:-%{_sysconfdir}/%{name}}

STOP_REQUIRED=false
REMOVE_SERVICE=false
# 0 for uninstall and 1 for upgrade
case "$1" in
0)
    STOP_REQUIRED=true
    REMOVE_SERVICE=true
    ;;
1)
    ;;
*)
    echo "pre remove script called with unknown argument \`$1'" >&2
    exit 1
    ;;
esac

if test "${STOP_REQUIRED}" = "true"; then
    echo -n "Stopping %{name} service..."
    systemctl --no-reload stop %{name}.service
    echo " OK"
fi

if test -f "${ES_PATH_CONF}/%{name}.keystore"; then
    if md5sum --status -c "${ES_PATH_CONF}"/.%{name}.keystore.initial_md5sum; then
        rm "${ES_PATH_CONF}"/%{name}.keystore "${ES_PATH_CONF}"/.%{name}.keystore.initial_md5sum
    fi
fi

if test "${REMOVE_SERVICE}" = "true"; then
    systemctl disable %{name}.service >/dev/null 2>&1 || true
fi


%postun
if test -f "%{_sysconfdir}/sysconfig/%{name}"; then
    source "%{_sysconfdir}/sysconfig/%{name}"
fi
export ES_PATH_CONF=${ES_PATH_CONF:-%{_sysconfdir}/%{name}}

REMOVE_DIRS=false
REMOVE_JVM_OPTIONS_DIRECTORY=false
REMOVE_USER_AND_GROUP=false
# 0 for uninstall and 1 for upgrade
case "$1" in
0)
    REMOVE_DIRS=true
    REMOVE_USER_AND_GROUP=true
    REMOVE_JVM_OPTIONS_DIRECTORY=true
    ;;
1)
    IS_UPGRADE=true
    ;;
*)
    echo "post remove script called with unknown argument \`$1'" >&2
    exit 1
    ;;
esac

if test "${REMOVE_DIRS}" = "true"; then
    if test -d %{_sysconfdir}/log/%{name}; then
        echo -n "Deleting log directory..."
        rm -rf %{_sysconfdir}/log/%{name}
        echo " OK"
    fi

    if test -d %{_datadir}/%{name}/plugins; then
        echo -n "Deleting plugins directory..."
        rm -rf %{_datadir}/%{name}/plugins
        echo " OK"
    fi
    # plugins may have contained bin files
    if test -d %{_datadir}/%{name}/bin; then
        echo -n "Deleting plugin bin directories..."
        rm -rf %{_datadir}/%{name}/bin
        echo " OK"
    fi

    if test -d /var/run/%{name}; then
        echo -n "Deleting PID directory..."
        rm -rf /var/run/%{name}
        echo " OK"
    fi
    # Delete the data directory if and only if empty
    if test -d %{_sharedstatedir}/%{name}; then
        rmdir --ignore-fail-on-non-empty "%{_sharedstatedir}/%{name}"
    fi
    # delete the jvm.options.d directory if and only if empty
    if test -d "${ES_PATH_CONF}/jvm.options.d"; then
        rmdir --ignore-fail-on-non-empty "${ES_PATH_CONF}/jvm.options.d"
    fi
    # delete the jvm.options.d directory if we are purging
    if test "${REMOVE_JVM_OPTIONS_DIRECTORY}" = "true" && test -d "${ES_PATH_CONF}/jvm.options.d"; then
        echo -n "Deleting jvm.options.d directory..."
        rm -rf "${ES_PATH_CONF}/jvm.options.d"
        echo " OK"
    fi
    # delete the conf directory if and only if empty
    if test -d "${ES_PATH_CONF}"; then
        rmdir --ignore-fail-on-non-empty "${ES_PATH_CONF}"
    fi

    find %{_sysconfdir}/rc.d/ -type l -name *%{name} -exec unlink {} \;
fi

if test "${REMOVE_USER_AND_GROUP}" = "true"; then
    if id %{name} >/dev/null 2>&1; then
        userdel %{name}
    fi

    if getent group %{name} >/dev/null 2>&1; then
        groupdel %{name}
    fi
fi


%posttrans
if test -f "%{_sysconfdir}/sysconfig/%{name}"; then
    source "%{_sysconfdir}/sysconfig/%{name}"
fi
export ES_PATH_CONF=${ES_PATH_CONF:-%{_sysconfdir}/%{name}}

if ! test -f "${ES_PATH_CONF}/%{name}.keystore"; then
    %{_datadir}/%{name}/bin/%{name}-keystore create
    chown root:%{name} "${ES_PATH_CONF}/%{name}.keystore"
    chmod 660 "${ES_PATH_CONF}/%{name}.keystore"
    md5sum "${ES_PATH_CONF}/%{name}.keystore" >"${ES_PATH_CONF}/.%{name}.keystore.initial_md5sum"
else
    if %{_datadir}/%{name}/bin/%{name}-keystore has-passwd --silent; then
        echo "# Warning: unable to upgrade encrypted keystore" 1>&2
        echo " Please run %{name}-keystore upgrade and enter password" 1>&2
    else
        %{_datadir}/%{name}/bin/%{name}-keystore upgrade
    fi
fi

# The users and groups created by the elastic component do not have a fixed uid or gid
# we need to ensure that the service can start normally after reinstalling.
chown -R %{name}:%{name} %{_sharedstatedir}/%{name} %{_localstatedir}/log/%{name}


%files
%license licenses/ELASTIC-LICENSE.txt
%doc NOTICE.txt README.asciidoc CONTRIBUTING.md
%dir %attr(02755, elasticsearch, elasticsearch) %{_sharedstatedir}/%{name}
%dir %attr(02755, elasticsearch, elasticsearch) %{_localstatedir}/log/%{name}
%dir %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}
# etc/elasticsearch/*
%dir %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/jvm.options.d
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/%{name}.yml
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/jvm.options
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/log4j2.properties
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/role_mapping.yml
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/roles.yml
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/users
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/%{name}/users_roles
%config(noreplace) %attr(-, root, elasticsearch) %{_sysconfdir}/sysconfig/%{name}
%config(noreplace) %{_sysconfdir}/init.d/%{name}
# elasticsearch home
%dir %{_datadir}/%{name}
%{_datadir}/%{name}/*
# sysctl and systemd unit file
%config(noreplace) %{_tmpfilesdir}/%{name}.conf
%config(noreplace) %{_sysctldir}/%{name}.conf
%{_unitdir}/%{name}.service


%changelog
