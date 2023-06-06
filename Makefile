
DESTDIR =
PREFIX = /usr/local
PROGRAM_PREFIX =

.PHONY: install
install:
	mkdir -p $(DESTDIR)$(PREFIX)/bin
	mkdir -p $(DESTDIR)$(PREFIX)/share/yosys/python3
	cp src/scy/scy_*.py $(DESTDIR)$(PREFIX)/share/yosys/python3/
	sed 's|##yosys-sys-path##|sys.path += [os.path.dirname(__file__) + p for p in ["/share/python3", "/../share/yosys/python3"]]|;' < src/scy/scy.py > $(DESTDIR)$(PREFIX)/bin/scy
	chmod +x $(DESTDIR)$(PREFIX)/bin/scy
