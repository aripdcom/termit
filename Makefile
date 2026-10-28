# Termit installation helpers.
#
#   make run              run from the source tree
#   make install          install for the current user (~/.local)
#   make install PREFIX=/usr/local   system-wide install (run with sudo)
#   make uninstall        remove the installed files
#   make lint             run ruff
#   make check            compile and import check
#   make bump VERSION=0.2.0   bump the version and prepare the changelog

PREFIX ?= $(HOME)/.local
BINDIR = $(PREFIX)/bin
LIBDIR = $(PREFIX)/share/termit
APPDIR = $(PREFIX)/share/applications
ICONDIR = $(PREFIX)/share/icons/hicolor/scalable/apps
METADIR = $(PREFIX)/share/metainfo
APP_ID = com.aripdcom.Termit
PYTHON ?= python3

.PHONY: run install uninstall lint check bump clean

run:
	$(PYTHON) -m termit

install:
	install -d $(LIBDIR)/termit/resources $(BINDIR) $(APPDIR) $(ICONDIR) $(METADIR)
	install -m 644 termit/*.py $(LIBDIR)/termit/
	install -m 644 termit/resources/* $(LIBDIR)/termit/resources/
	printf '#!/bin/sh\nexec $(PYTHON) -c "import sys; sys.path.insert(0, \"$(LIBDIR)\"); from termit.main import main; sys.exit(main())" "$$@"\n' > $(BINDIR)/termit
	chmod 755 $(BINDIR)/termit
	install -m 644 data/$(APP_ID).desktop $(APPDIR)/
	install -m 644 data/icons/hicolor/scalable/apps/$(APP_ID).svg $(ICONDIR)/
	install -m 644 data/$(APP_ID).metainfo.xml $(METADIR)/
	-update-desktop-database $(APPDIR) 2>/dev/null
	-gtk-update-icon-cache -q -t $(PREFIX)/share/icons/hicolor 2>/dev/null
	@echo "Installed. Run 'termit' or launch Termit from the application grid."

uninstall:
	rm -rf $(LIBDIR)
	rm -f $(BINDIR)/termit $(APPDIR)/$(APP_ID).desktop $(ICONDIR)/$(APP_ID).svg $(METADIR)/$(APP_ID).metainfo.xml

lint:
	ruff check termit

check:
	$(PYTHON) -m compileall -q termit
	$(PYTHON) -c "import termit.main"

bump:
	@test -n "$(VERSION)" || (echo "usage: make bump VERSION=X.Y.Z" && exit 1)
	$(PYTHON) scripts/bump_version.py $(VERSION)

clean:
	find . -name __pycache__ -type d -exec rm -rf {} +
