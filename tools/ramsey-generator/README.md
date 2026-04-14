# Ramsey SAT Formula Generator

Courtesy of Marijn Heule. Generates SAT formulas with controllable difficulty.

## Compile

```bash
gcc ramsey-generator.c -O2 -o ramsey-generator
```

## Usage

```bash
# Easy satisfiable (~small)
./ramsey-generator 25 3 11 > sat.cnf

# Easy unsatisfiable (~small)
./ramsey-generator 170 3 4 > unsat.cnf

# Small but hard (runs forever)
./ramsey-generator 42 5 5 > hard.cnf

# Huge formula (6.5GB)
./ramsey-generator 30 3 10 > huge.cnf
```

Increasing the first number makes formulas larger. SAT formulas grow very fast.
