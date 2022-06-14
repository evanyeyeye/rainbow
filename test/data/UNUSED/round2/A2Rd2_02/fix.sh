#!/bin/bash

for i in *.arw; do
    awk -f fix.awk $i > temp.arw
    mv temp.arw $i
done
