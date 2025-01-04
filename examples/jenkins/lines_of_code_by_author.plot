set terminal png transparent size 640,240
set size 1.0,1.0

set terminal png transparent size 640,480
set output 'lines_of_code_by_author.png'
set key left top
set yrange [0:]
set xdata time
set timefmt "%s"
set format x "%Y-%m-%d"
set grid y
set ylabel "Lines"
set xtics rotate
set bmargin 6
plot 'lines_of_code_by_author.dat' using 1:2 title "kohsuke" w lines, 'lines_of_code_by_author.dat' using 1:3 title "Kohsuke Kawaguchi" w lines, 'lines_of_code_by_author.dat' using 1:4 title "Jesse Glick" w lines, 'lines_of_code_by_author.dat' using 1:5 title "Daniel Beck" w lines, 'lines_of_code_by_author.dat' using 1:6 title "Oleg Nenashev" w lines, 'lines_of_code_by_author.dat' using 1:7 title "dependabot[bot]" w lines, 'lines_of_code_by_author.dat' using 1:8 title "renovate[bot]" w lines, 'lines_of_code_by_author.dat' using 1:9 title "Basil Crow" w lines, 'lines_of_code_by_author.dat' using 1:10 title "Oliver Gondža" w lines, 'lines_of_code_by_author.dat' using 1:11 title "Stephen Connolly" w lines, 'lines_of_code_by_author.dat' using 1:12 title "Jenkins Release Bot" w lines, 'lines_of_code_by_author.dat' using 1:13 title "mindless" w lines, 'lines_of_code_by_author.dat' using 1:14 title "Olivier Lamy" w lines, 'lines_of_code_by_author.dat' using 1:15 title "Tim Jacomb" w lines, 'lines_of_code_by_author.dat' using 1:16 title "sogabe" w lines, 'lines_of_code_by_author.dat' using 1:17 title "Christoph Kutzinski" w lines, 'lines_of_code_by_author.dat' using 1:18 title "tfennelly" w lines, 'lines_of_code_by_author.dat' using 1:19 title "Wadeck Follonier" w lines, 'lines_of_code_by_author.dat' using 1:20 title "Baptiste Mathus" w lines, 'lines_of_code_by_author.dat' using 1:21 title "Vincent Latombe" w lines
