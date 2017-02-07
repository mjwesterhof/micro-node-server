# Makefile - micro-node-server

# Edit this to point to your micropython cross compiler
MPY_CROSS=/s/src/micropython/mpy-cross/mpy-cross

# Add your own modules to this line
MPYS=unsmain.mpy unslib.mpy

# Rules follow...

all:	$(MPYS)	

clean:
	$(RM) $(MPYS)

%.mpy: %.py
	$(MPY_CROSS) -o $@ $^
