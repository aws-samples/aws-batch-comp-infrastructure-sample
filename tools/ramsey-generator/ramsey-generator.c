// courtesy of Marijn Heule

#include <stdio.h>
#include <stdlib.h>
#include <assert.h>

#define SBP

int edge (int a, int b) {
  assert (a != b);
  assert (a >  0);
  assert (b >  0);
  int min, max;
  min = a; max = b;
  if (min > max) { min = b; max = a; }

  return (max - 2) * (max - 1) / 2 + min; }

void printClique (int *nodes, int size, int maxNode, int color) {
  int i, j;

  for (i = 0; i < size; i++)
    for (j = i + 1; j < size; j++)
      if (color == -1) printf ("%i ",  edge (nodes[i], nodes[j]));
      else             printf ("%i ", -edge (nodes[i], nodes[j]) - maxNode * (maxNode-1) * color / 2);

  printf ("0\n"); }

void addNodeRec (int *nodes, int size, int maxSize, int maxNode, int color) {
  if (size == maxSize) {
    printClique (nodes, size, maxNode, color); }
  else {
    int i, start = 0;
    if (size > 0) start = nodes[size - 1];
    for (i = start + 1; i <= maxNode; i++) {
      nodes[size] = i;
      addNodeRec (nodes, size + 1, maxSize, maxNode, color); } } }

int main (int argc, char** argv) {

  int nColor = argc - 2;

  if (nColor < 1) {
    printf ("c too few arguments: ./Ramsey #Node Color_1 [Color_2 ... Color_k]\n");
    exit (0); }

  int nNode  = atoi (argv[1]);

  int i, j, k, max, clique[nColor];
  int nVar, nCls;

  if (nColor <= 2) { nCls = 0; nVar = nNode * (nNode - 1) / 2; }
  else             { nCls = nNode + nNode * nColor * (nColor - 1) / 2; nVar = nColor * nNode * (nNode - 1) / 2; }

  max = 0;
  for (i = 0; i < nColor; i++) {
    clique[i] = atoi (argv[i+2]);
    if (clique[i] > max) max = clique[i];
    assert (clique[i] <= nNode); }

  for (i = 0; i < nColor; i++) {
    int product = 1;
    for (j = 0; j < clique[i]; j++) { product *= (nNode - j); product /= (j+1); }
    nCls += product; }

#ifdef SBP
  if (nColor == 2) nCls += nNode - 2;
#endif

  printf ("p cnf %i %i\n", nVar, nCls);

#ifdef SBP
  for (int i = 2; i < nNode; i++)
    printf ("%i -%i 0\n", edge (1,i), edge (1, i+1));

//  for (int i = 3; i < nNode; i++)
//    printf ("-%i %i -%i 0\n", edge (1,i+1), edge (2,i), edge (2, i+1));

//  for (int i = nNode-1; i > 2; i--)
//    printf ("%i -%i %i 0\n", edge (1,i-1), edge (nNode,i), edge (nNode, i-1));
#endif

  if (nColor > 2) {
   for (i = 1; i <= nNode * (nNode - 1) / 2; i++) {
     for (j = 0; j < nColor; j++)
       printf ("%i ", j * nNode * (nNode - 1) / 2 + i);
     printf("0\n");
     for (j = 0; j < nColor; j++)
       for (k = j+1; k < nColor; k++)
         printf ("-%i -%i 0\n", j * nNode * (nNode - 1) / 2 + i, k * nNode * (nNode - 1) / 2 + i); } }

  int nodes[max];
  for (i = 1; i <= max; i++)
    nodes[i-1] = i;

  if (nColor <= 2) {
                     addNodeRec (nodes, 0, clique[0], nNode, -1);
    if (nColor == 2) addNodeRec (nodes, 0, clique[1], nNode,  0);
  }
  else {
    for (i = 0; i < nColor; i++)
      addNodeRec (nodes, 0, clique[i], nNode, i); }

}
