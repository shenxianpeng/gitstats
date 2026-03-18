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
Type "gitstats . report"
Sleep 300ms
Enter
Sleep 15s

# Step 4: Show the generated output files
Type "python3 -m http.server 8000 --bind 127.0.0.1 -d /workspaces/gitstats/report"
Sleep 300ms
Enter
Sleep 2s

# Done
Sleep 3s
