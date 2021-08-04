%global         debug_package   %{nil}
%global         build_java      java-11-openjdk
%global         runtime_java    jre-11-openjdk

%bcond_with     details
%bcond_with     tests

Name:           logstash
Version:        7.10.0
Release:        1
Summary:        An extensible logging pipeline
Group:          default
License:        Elastic License
URL:            https://www.elastic.co/%{name}
Source0:        https://github.com/elastic/%{name}/archive/refs/tags/v%{version}.tar.gz

Patch0:         fix-build.patch

BuildRequires:  expect %{build_java}-devel
AutoReqProv:    no
Requires:       %{runtime_java}

%description
Logstash is part of the Elastic Stack along with Beats, Elasticsearch and Kibana.
Logstash is a server-side data processing pipeline that ingests data from a 
multitude of sources simultaneously, transforms it, and then sends it to your 
favorite "stash." (Ours is Elasticsearch, naturally.). Logstash has over 200 
plugins, and you can write your own very easily as well.


%prep
%autosetup -p1
# Do not directly use java in the system, it may be version 1.8.0
sed -ri '/JAVACMD/cJAVACMD=%{_jvmlibdir}\/%{runtime_java}\/bin\/java' config/startup.options


%build
export JAVA_HOME="%{_jvmlibdir}/%{build_java}"

expect <<EOF
set timeout 7200
spawn ./gradlew clean build assembleTarDistribution -x test %{?with_details:-stacktrace -debug -scan} %{!?with_details:-info}
expect {
    "Publishing a build scan to scans.gradle.com requires accepting the Gradle Terms*yes*no" { send "yes\r"; exp_continue}
}
EOF


%check
%if 0%{?with_tests:1}
    ./gradlew test
%endif


%install
tar xf build/%{name}-%{version}-SNAPSHOT.tar.gz -C build/
pushd build/%{name}-%{version}-SNAPSHOT || exit 1
# remove useless shared object
test -d vendor/jruby/lib/jni && \
    find vendor/jruby/lib/jni/* -maxdepth 1 -type d \
    ! -name "$(uname -m)-$(uname)" | xargs -i rm -rf {}

install -d -p -m 0755 %{buildroot}%{_sharedstatedir}/%{name}
install -d -p -m 0755 %{buildroot}%{_var}/log/%{name}
install -d -p -m 0755 %{buildroot}%{_sysconfdir}/%{name}/conf.d
install -d -p -m 0755 %{buildroot}%{_datadir}/%{name}

install -D -p -m 0644 config/* %{buildroot}%{_sysconfdir}/%{name}
rm -rf config
find -type f -iname "*.bat" -exec rm {} \;
cp -a * %{buildroot}%{_datadir}/%{name}/


%pre
# create logstash group
if ! getent group %{name} >/dev/null; then
    groupadd -r %{name}
fi
# create logstash user
if ! getent passwd %{name} >/dev/null; then
    useradd -r -g %{name} -d %{_datadir}/%{name} \
        -s /sbin/nologin -c "%{name}" %{name}
fi


%preun
if test "$1" = "0"; then
    systemctl --no-reload stop %{name}.service
    systemctl disable %{name}.service >/dev/null 2>&1 || true
    test -f "%{_sysconfdir}/systemd/system/%{name}-prestart.sh" &&
        rm %{_sysconfdir}/systemd/system/%{name}-prestart.sh || true
    getent passwd %{name} >/dev/null && userdel %{name}
    getent group %{name} >/dev/null && groupdel %{name}
    # Ignore the error code that the user or user group cannot be found
    true
fi


%post
chown -R %{name}:%{name} %{_datadir}/%{name}
chown -R %{name} %{_var}/log/%{name}
chown -R %{name}:%{name} %{_sharedstatedir}/%{name}
%{_datadir}/%{name}/bin/system-install %{_sysconfdir}/%{name}/startup.options
chmod 600 %{_sysconfdir}/%{name}/startup.options
chmod 600 %{_sysconfdir}/default/%{name}


%postun
if test "$1" == "0"; then
    # delete files generated during installation
    rm -f %{_sysconfdir}/systemd/system/%{name}.service
    rm -f %{_sysconfdir}/default/%{name}
    rm -f %{_sysconfdir}/sysconfig/%{name}
fi


%files
%license licenses/APACHE-LICENSE-2.0.txt licenses/ELASTIC-LICENSE.txt
%dir %{_datadir}/%{name}
%dir %{_sysconfdir}/%{name}
%dir %{_sharedstatedir}/%{name}
%dir %{_var}/log/%{name}
%{_datadir}/%{name}/*
%dir %{_sysconfdir}/%{name}/conf.d
%config(noreplace) %{_sysconfdir}/%{name}/jvm.options
%config(noreplace) %{_sysconfdir}/%{name}/log4j2.properties
%config(noreplace) %{_sysconfdir}/%{name}/logstash-sample.conf
%config(noreplace) %{_sysconfdir}/%{name}/%{name}.yml
%config(noreplace) %{_sysconfdir}/%{name}/pipelines.yml
%config(noreplace) %{_sysconfdir}/%{name}/startup.options


%changelog
