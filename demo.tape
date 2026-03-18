# demo.tape — record a gitstats demo GIF
# Generate with: vhs demo.tape

Output demo.gif

Set Shell "bash"
Set FontSize 16
Set Width 1200
Set Height 700
Set Theme "Dracula"
Set Padding 20
Set TypingSpeed 40ms

# Start in a fresh shell with the repo cloned
Hide
Type "cd /tmp && git clone https://github.com/shenxianpeng/gitstats.git demo-repo 2>&1 | tail -1"
Enter
Sleep 5s
Show

# Step 1: Install gitstats
Type "pip install gitstats"
Sleep 500ms
Enter
Sleep 8s

# Step 2: Show help
Type "gitstats --help"
Sleep 300ms
Enter
Sleep 3s

# Step 3: Generate a report for the cloned repo
Type "gitstats demo-repo report"
Sleep 300ms
Enter
Sleep 15s

# Step 4: Show the generated output files
Type "ls report/"
Sleep 300ms
Enter
Sleep 2s

# Done
Sleep 3s
