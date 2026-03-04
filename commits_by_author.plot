set terminal png transparent size 640,240
set size 1.0,1.0
set linetype 1 lc rgb '#5b8dee'
set linetype 2 lc rgb '#1a7f37'
set linetype 3 lc rgb '#cf222e'
set linetype 4 lc rgb '#8250df'
set linetype 5 lc rgb '#e16f24'
set linetype 6 lc rgb '#0550ae'

set terminal png transparent size 640,480
set output 'commits_by_author.png'
set key left top
set yrange [0:]
set xdata time
set timefmt "%s"
set format x "%Y-%m-%d"
set grid y
set ylabel "Commits"
set xtics rotate
set bmargin 6
plot 'commits_by_author.dat' using 1:2 title "Heikki Hokkanen" w lines, 'commits_by_author.dat' using 1:3 title "Xianpeng Shen" w lines, 'commits_by_author.dat' using 1:4 title "dependabot[bot]" w lines, 'commits_by_author.dat' using 1:5 title "Wulf C. Krueger" w lines, 'commits_by_author.dat' using 1:6 title "Matthieu Moy" w lines, 'commits_by_author.dat' using 1:7 title "Tobias Gruetzmacher" w lines, 'commits_by_author.dat' using 1:8 title "Sven van Haastregt" w lines, 'commits_by_author.dat' using 1:9 title "Copilot" w lines, 'commits_by_author.dat' using 1:10 title "Jani Hur" w lines, 'commits_by_author.dat' using 1:11 title "Alexander Strasser" w lines, 'commits_by_author.dat' using 1:12 title "pre-commit-ci[bot]" w lines, 'commits_by_author.dat' using 1:13 title "Tyler Nielsen" w lines, 'commits_by_author.dat' using 1:14 title "Sylvain Joyeux" w lines, 'commits_by_author.dat' using 1:15 title "Stephen Gordon" w lines, 'commits_by_author.dat' using 1:16 title "Shixin Zeng" w lines, 'commits_by_author.dat' using 1:17 title "Kirill Chilikin" w lines, 'commits_by_author.dat' using 1:18 title "Thomas R. Koll" w lines, 'commits_by_author.dat' using 1:19 title "Stephan Kuschel" w lines, 'commits_by_author.dat' using 1:20 title "Stefano Mosconi" w lines, 'commits_by_author.dat' using 1:21 title "Richard Russon (flatcap)" w lines
