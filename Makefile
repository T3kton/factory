VERSION := $(shell head -n 1 debian/changelog | awk '{match( $$0, /\(.+?\)/); print substr( $$0, RSTART+1, RLENGTH-2 ) }' | cut -d- -f1 )

all: build-ui
	./setup.py build

install: install-ui
	mkdir -p $(DESTDIR)/var/www/factory/api
	mkdir -p $(DESTDIR)/etc/apache2/sites-available
	mkdir -p $(DESTDIR)/etc/factory
	mkdir -p $(DESTDIR)/usr/lib/factory/cron
	mkdir -p $(DESTDIR)/usr/lib/factory/util
	mkdir -p $(DESTDIR)/usr/lib/factory/setup

	install -m 644 api/factory.wsgi $(DESTDIR)/var/www/factory/api
	install -m 644 apache.conf $(DESTDIR)/etc/apache2/sites-available/factory.conf
	install -m 644 factory.conf.sample $(DESTDIR)/etc
	install -m 755 lib/cron/* $(DESTDIR)/usr/lib/factory/cron
	install -m 755 lib/util/* $(DESTDIR)/usr/lib/factory/util
	install -m 755 lib/setup/* $(DESTDIR)/usr/lib/factory/setup

	./setup.py install --root=$(DESTDIR) --install-purelib=/usr/lib/python3/dist-packages/ --prefix=/usr --no-compile -O0

version:
	echo $(VERSION)

clean: clean-ui
	./setup.py clean || true
	$(RM) -r build
	$(RM) dpkg
	$(RM) -r htmlcov
	dh_clean || true
	find -name *.pyc -delete
	find -name __pycache__ -delete

dist-clean: clean

.PHONY:: all install version clean dist-clean

ui_files := $(foreach file,$(wildcard ui/src/www/*),ui/build/$(notdir $(file)))

build-ui: ui/build/bundle.js $(ui_files)

ui/build/bundle.js: $(wildcard ui/src/frontend/component/*) ui/src/frontend/index.js
	cd ui && npm run build

ui/build/%:
	cp ui/src/www/$(notdir $@) $@

install-ui: build-ui
	mkdir -p $(DESTDIR)/var/www/factory/ui/
	install -m 644 ui/build/* $(DESTDIR)/var/www/factory/ui/
	echo "window.API_BASE_URI = window.location.protocol + '//' + window.location.host;" > $(DESTDIR)/var/www/factory/ui/env.js

clean-ui:
	$(RM) -fr ui/build

.PHONY:: build-ui install-ui clean-ui

test-blueprints:
	echo ubuntu-focal-base

test-requires:
	echo flake8 python3-pip python3-django python3-psycopg2 python3-pymongo python3-parsimonious python3-jinja2 python3-pytest python3-pytest-cov python3-pytest-django python3-pytest-mock python3-pytest-timeout postgresql mongodb

test-setup:
	su postgres -c "echo \"CREATE ROLE factory WITH PASSWORD 'factory' NOSUPERUSER NOCREATEROLE CREATEDB LOGIN;\" | psql"
	pip3 install -e .
	cp factory.conf.sample factory/settings.py
	touch test-setup

lint:
	flake8 --ignore=E501,E201,E202,E111,E126,E114,E402,W503 --statistics --exclude=migrations,build .

test:
	py.test-3 -x --cov=factory --cov-report html --cov-report term --ds=factory.settings -vv factory

.PHONY:: test-blueprints test-requires lint test

dpkg-blueprints:
	echo ubuntu-focal-base

dpkg-requires:
	echo dpkg-dev debhelper python3-dev python3-setuptools nodejs npm dh-python

dpkg-setup:
ifeq (1, $(NULLUNIT))
	npm install -g npm@5
	mv /usr/bin/npm  /usr/bin/npm.old
endif
	cd ui && npm install
	sed s/"export Ripple from '.\/ripple';"/"export { default as Ripple } from '.\/ripple';"/ -i ui/node_modules/react-toolbox/components/index.js
	sed s/"export Tooltip from '.\/tooltip';"/"export { default as Tooltip } from '.\/tooltip';"/ -i ui/node_modules/react-toolbox/components/index.js

dpkg:
	dpkg-buildpackage -b -us -uc
	touch dpkg

dpkg-file:
	echo $(shell ls ../factory_*.deb):focal

.PHONY:: dpkg-blueprints dpkg-requires dpkg dpkg-file
