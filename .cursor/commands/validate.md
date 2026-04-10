--- Cursor Command: validate ---
This command performs deep code analysis to find potential bugs, edge cases, and logic errors.

Instructions:
1. Analyze the currently open file or selected code
2. Look for common bug patterns:
   - Early returns that skip important logic
   - Division by zero or empty collection operations
   - Missing null/undefined checks
   - Race conditions and timing issues
   - Resource leaks (unclosed connections, files)
   - Off-by-one errors
   - Type mismatches and conversion issues
   - Missing error handling
   - Double counting or duplicate operations
   - Cache/state consistency issues
   - Edge cases with empty inputs
   - ThreadPool/Worker pool with zero workers
   - Incorrect date/time handling

3. Check for logic issues:
   - Defensive checks that suggest edge cases but aren't fully handled
   - Comments acknowledging issues but not fixing them
   - Dead code after early returns
   - Inconsistent state updates
   - Order-dependent operations (initialization order matters)

4. For each issue found, provide:
   - File path and line numbers
   - Severity: High/Medium/Low
   - Clear description of the problem
   - Why it can happen (what scenario triggers it)
   - Impact on functionality

5. Format output as:
   ```
   {file_path}#{line_start}-{line_end}
   {Issue title}
   {Severity} Severity
   
   {Detailed explanation with code references}
   ```

6. Focus on:
   - Real bugs that will crash or produce wrong results
   - Edge cases that are likely to occur
   - NOT style issues or minor improvements

7. Consider the full context - read related functions if needed

8. If no issues found, respond: "No critical issues detected."

--- End Command ---
