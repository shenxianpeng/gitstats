set terminal png transparent size 640,240
set size 1.0,1.0
set linetype 1 lc rgb '#5b8dee'
set linetype 2 lc rgb '#1a7f37'
set linetype 3 lc rgb '#cf222e'
set linetype 4 lc rgb '#8250df'
set linetype 5 lc rgb '#e16f24'
set linetype 6 lc rgb '#0550ae'

set output 'commits_by_year.png'
unset key
set yrange [0:]
set xtics 1 rotate
set grid y
set ylabel "Commits"
set yrange [0:]
plot 'commits_by_year.dat' using 1:2:(0.5) w boxes fs solid
