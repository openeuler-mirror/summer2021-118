%global         debug_package   %{nil}
# When kibana is upgraded, the value may need to be reset
%global         min_nodejs      10.21.0
%global         min_yarn        1.21.1
%global         build_java      java-11-openjdk
%global         templates_dir   src/dev/build/tasks/os_packages/service_templates
%global         sysv_path       %{templates_dir}/sysv
%global         sysd_path       %{templates_dir}/systemd

Name:           kibana
Version:        7.9.0
Release:        2
Group:          default
Summary:        Explore and visualize your Elasticsearch data

License:        Elastic License
URL:            https://www.elastic.co/%{name}
Source0:        https://github.com/elastic/%{name}/archive/refs/tags/v%{version}.tar.gz

Patch0:         update-dependencies-list.patch
Patch1:         generate-for-current-platform.patch
Patch2:         use-node-provides-by-os.patch
Patch3:         disable-download-chromium.patch

BuildRequires:  nodejs >= %{min_nodejs}, yarn >= %{min_yarn}, %{build_java}-devel
BuildRequires:  git

Requires:       nodejs >= %{min_nodejs}

%description
Kibana is a free and open user interface that lets you visualize your
Elasticsearch data and navigate the Elastic Stack. Do anything from tracking
query load to understanding the way requests flow through your apps.


%prep
%autosetup -p1
exit 0
# use the version of node in the system to replace the node version in sources
node -v | sed -r 's/[a-zA-Z\-_]//g' >.node-version
sed -ri '/"node"/s/(^.*\"node\": \").*(\".*$)/\1'$(cat .node-version)'\2/' package.json
# Compilation should be done in a git repository
%{__scm_setup_git} >/dev/null


%build
export JAVA_HOME="%{_jvmlibdir}/%{build_java}"
# skip download chromium browser
export PUPPETEER_SKIP_CHROMIUM_DOWNLOAD=true
# download dependences
yarn add build
# Some dependent modules need to be compiled in advance
function build_kbn_module() {
    local module_name="$1"
    local cmdstr="${2:-build}"
    test -z "${module_name}" && return
    pushd node_modules/@kbn/${module_name} || exit 1
    yarn "${cmdstr}"
    popd
}
kbn_modules=("dev-utils" "optimizer" "i18n" "config-schema" "babel-code-parser")
for kbn_module in "${kbn_modules[@]}"; do
    build_kbn_module "${kbn_module}"
done

build_kbn_module "plugin-helpers" "kbn:bootstrap"

yarn build --skip-os-packages \
    --skip-archives \
    --no-oss \
    --skip-docker-ubi \
    --skip-node-download \
    --release \
    --verbose


%install
# process default generations
cp NOTICE.txt "./build/%{name}/"
install -d -p -m 0755 %{buildroot}%{_sysconfdir}/%{name} %{buildroot}%{_datadir}/%{name}

pushd "./build/%{name}" || exit 1
find ./ -type f -iname "*.bat"  -exec rm -f {} \;
# etc/kibana
install -D -p -m 0644 config/* %{buildroot}%{_sysconfdir}/%{name}
rm -rf config
# usr/share
cp -p bin/%{name}-keystore bin/%{name}-encryption-keys
sed -i '/^NODE_OPTIONS/s#cli_keystore#cli_encryption_keys#' bin/%{name}-encryption-keys
cp -a * %{buildroot}%{_datadir}/%{name}/
popd
# systemd
install -d -p -m 0755 %{buildroot}%{_unitdir} 
install -D -p -m 0644 %{sysd_path}/etc/systemd/system/%{name}.service %{buildroot}%{_unitdir}
# tmpfiles
install -d -p -m 0755 %{buildroot}%{_tmpfilesdir}
install -D -p -m 0644 %{sysd_path}%{_tmpfilesdir}/%{name}.conf %{buildroot}%{_tmpfilesdir}
# run
install -d -p -m 0755 %{buildroot}%{_rundir}/%{name}
# var
install -d -p -m 0755 %{buildroot}%{_sharedstatedir}/%{name}
# etc
install -d -p -m 0755 %{buildroot}%{_initddir} %{buildroot}%{_sysconfdir}/sysconfig
install -D -p -m 0755 %{sysv_path}/etc/init.d/%{name}   %{buildroot}%{_initddir}
install -D -p -m 0644 %{sysv_path}/etc/default/%{name}  %{buildroot}%{_sysconfdir}/sysconfig


%pre
set -e
if systemctl is-active %{name}.service >/dev/null; then
    systemctl --no-reload stop %{name}.service
fi


%post
set -e
export KBN_PATH_CONF=${KBN_PATH_CONF:-%{_sysconfdir}/%{name}}
case $1 in
1 | 2)
    if ! getent group %{name} >/dev/null; then
        groupadd -r "%{name}"
    fi
    if ! getent passwd %{name} >/dev/null; then
        useradd -r -g "%{name}" -M -s /sbin/nologin -c "%{name} service user" %{name}
    fi

    if test "$1" = "2"; then
        IS_UPGRADE=true
    fi
    chmod -f 660 ${KBN_PATH_CONF}/%{name}.yml || true
    chmod -f 2750 %{_sharedstatedir}/%{name} || true
    chmod -f 2750 ${KBN_PATH_CONF} || true
    chown -R %{name}:%{name} %{_sharedstatedir}/%{name}
    chown -R root:%{name} ${KBN_PATH_CONF}
    chown -R %{name}:%{name} %{_datadir}/%{name}/data
    ;;
*)
    echo "post install script called with unknown argument \`$1'" >&2
    exit 1
    ;;
esac

if test "${IS_UPGRADE}" = "true"; then
    systemctl daemon-reload
fi


%preun
echo -n "Stopping %{name} service..."
if systemctl is-active %{name}.service >/dev/null; then
    systemctl --no-reload stop %{name}.service
fi
echo " OK"


%postun
REMOVE_USER_AND_GROUP=false
REMOVE_DIRS=false

case $1 in
0)
    REMOVE_USER_AND_GROUP=true
    REMOVE_DIRS=true
    ;;
1) 
    ;;
*)
    echo "post remove script called with unknown argument \`$1'" >&2
    exit 1
    ;;
esac

if test "${REMOVE_USER_AND_GROUP}" = "true"; then
    if getent passwd %{name} >/dev/null; then
        userdel %{name}
    fi
    if getent group %{name} >/dev/null; then
        groupdel %{name}
    fi
fi

if test "${REMOVE_DIRS}" = "true"; then
    if test -d "%{_datadir}/%{name}/optimize"; then
        rm -rf "%{_datadir}/%{name}/optimize"
    fi
    if test -d "%{_datadir}/%{name}/plugins"; then
        rm -rf "%{_datadir}/%{name}/plugins"
    fi
    if test -d "%{_datadir}/%{name}/.chromium"; then
        rm -rf "%{_datadir}/%{name}/.chromium"
    fi
    if test -d "%{_sysconfdir}/%{name}"; then
        rmdir --ignore-fail-on-non-empty "%{_sysconfdir}/%{name}"
    fi
    if test -d "%{_sharedstatedir}/%{name}"; then
        rmdir --ignore-fail-on-non-empty "%{_sharedstatedir}/%{name}"
    fi
fi


%files
%license licenses/ELASTIC-LICENSE.txt
%doc README.md STYLEGUIDE.md CONTRIBUTING.md FAQ.md TYPESCRIPT.md
%dir %{_datadir}/%{name}
%dir %{_sysconfdir}/%{name}
%dir %{_rundir}/%{name}
%dir %{_sharedstatedir}/%{name}
%dir %{_initddir}
%dir %{_sysconfdir}/sysconfig
%{_datadir}/%{name}/*
%{_unitdir}/%{name}.service
%config(noreplace) %{_initddir}/%{name}
%config(noreplace) %{_sysconfdir}/%{name}/%{name}.yml
%config(noreplace) %{_sysconfdir}/%{name}/node.options
%config(noreplace) %{_tmpfilesdir}/%{name}.conf
%config(noreplace) %{_sysconfdir}/sysconfig/%{name}


%changelog
