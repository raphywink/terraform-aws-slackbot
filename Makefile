all: test validate

clean:
	make -C functions/default $@
	make -C functions/edge $@

ipython:
	make -C functions/edge $@

logs:
	make -C example $@

test:
	make -C functions/default $@
	make -C functions/edge $@

validate:
	terraform fmt -check
	make -C example $@

apply:
	make -C example $@

.PHONY: all clean ipython logs test validate apply
