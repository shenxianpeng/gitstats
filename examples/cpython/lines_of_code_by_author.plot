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
plot 'lines_of_code_by_author.dat' using 1:2 title "Guido van Rossum" w lines, 'lines_of_code_by_author.dat' using 1:3 title "Victor Stinner" w lines, 'lines_of_code_by_author.dat' using 1:4 title "Benjamin Peterson" w lines, 'lines_of_code_by_author.dat' using 1:5 title "Georg Brandl" w lines, 'lines_of_code_by_author.dat' using 1:6 title "Fred Drake" w lines, 'lines_of_code_by_author.dat' using 1:7 title "Serhiy Storchaka" w lines, 'lines_of_code_by_author.dat' using 1:8 title "Raymond Hettinger" w lines, 'lines_of_code_by_author.dat' using 1:9 title "Antoine Pitrou" w lines, 'lines_of_code_by_author.dat' using 1:10 title "Jack Jansen" w lines, 'lines_of_code_by_author.dat' using 1:11 title "Martin v. Löwis" w lines, 'lines_of_code_by_author.dat' using 1:12 title "Tim Peters" w lines, 'lines_of_code_by_author.dat' using 1:13 title "Brett Cannon" w lines, 'lines_of_code_by_author.dat' using 1:14 title "Barry Warsaw" w lines, 'lines_of_code_by_author.dat' using 1:15 title "Andrew M. Kuchling" w lines, 'lines_of_code_by_author.dat' using 1:16 title "Ezio Melotti" w lines, 'lines_of_code_by_author.dat' using 1:17 title "Mark Dickinson" w lines, 'lines_of_code_by_author.dat' using 1:18 title "Neal Norwitz" w lines, 'lines_of_code_by_author.dat' using 1:19 title "Christian Heimes" w lines, 'lines_of_code_by_author.dat' using 1:20 title "Terry Jan Reedy" w lines, 'lines_of_code_by_author.dat' using 1:21 title "Gregory P. Smith" w lines
