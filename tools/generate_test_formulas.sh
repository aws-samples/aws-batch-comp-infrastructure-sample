#!/bin/bash
# Generate all test formulas for acceptance testing and distributed testing.
# Run from the repo root: ./tools/generate_test_formulas.sh
#
# This compiles the Ramsey generator and creates benchmark CNF files
# in test_formulas/cnf/ for use by the acceptance test suite.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
GEN_DIR="$SCRIPT_DIR/ramsey-generator"
OUT_DIR="$REPO_ROOT/test_formulas/cnf"

mkdir -p "$OUT_DIR"

# Compile the Ramsey generator if needed
if [ ! -f "$GEN_DIR/ramsey-generator" ]; then
    echo "Compiling Ramsey generator..."
    gcc "$GEN_DIR/ramsey-generator.c" -O2 -o "$GEN_DIR/ramsey-generator"
fi

GEN="$GEN_DIR/ramsey-generator"

echo "Generating test formulas in $OUT_DIR..."

# --- Easy SAT formula ---
# Small satisfiable Ramsey instance
if [ ! -f "$OUT_DIR/sat_small_01.cnf" ]; then
    echo "  Generating sat_small_01.cnf (easy SAT)..."
    $GEN 8 3 4 > "$OUT_DIR/sat_small_01.cnf"
fi

# --- Easy UNSAT formula ---
# Small unsatisfiable Ramsey instance
if [ ! -f "$OUT_DIR/unsat_small_01.cnf" ]; then
    echo "  Generating unsat_small_01.cnf (easy UNSAT)..."
    $GEN 9 3 3 > "$OUT_DIR/unsat_small_01.cnf"
fi

# --- Timeout formula (hard, won't solve in 30s) ---
if [ ! -f "$OUT_DIR/timeout_hard_01.cnf" ]; then
    echo "  Generating timeout_hard_01.cnf (hard, ~78MB)..."
    $GEN 42 5 5 > "$OUT_DIR/timeout_hard_01.cnf"
fi

# --- OOM formula (causes memory exhaustion) ---
if [ ! -f "$OUT_DIR/oom_large_01.cnf" ]; then
    echo "  Generating oom_large_01.cnf (200M variables, tiny on disk, huge in memory)..."
    python3 -c "
n_vars = 200_000_000
n_clauses = 3
print(f'p cnf {n_vars} {n_clauses}')
print('1 2 3 0')
print(f'-1 -{n_vars} 0')
print(f'{n_vars-1} {n_vars} 0')
" > "$OUT_DIR/oom_large_01.cnf"
fi

# --- Malformed formula ---
if [ ! -f "$OUT_DIR/malformed_bad_header_01.cnf" ]; then
    echo "  Generating malformed_bad_header_01.cnf..."
    cat > "$OUT_DIR/malformed_bad_header_01.cnf" << 'EOF'
This is not a CNF file at all.
It contains no valid DIMACS header or clauses.
Just plain English text that no SAT solver should accept.
%^&*@#! random garbage: §±≠∞µ∂ƒ©˙∆˚¬
EOF
fi

echo ""
echo "Done! Generated formulas:"
ls -lh "$OUT_DIR"/*.cnf
echo ""
echo "To run acceptance tests: ./satcomp.py <config.yml> --test [solver-name]"
