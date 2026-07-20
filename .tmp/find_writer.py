with open('app/prompts/defaults.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find writer system_template boundaries
writer_start = None
for i, line in enumerate(lines):
    if '"writer"' in line:
        for j in range(i, min(i+10, len(lines))):
            if 'system_template' in lines[j]:
                writer_start = j
                break
        break

writer_end = None
for i in range(writer_start+1, len(lines)):
    if lines[i].strip() == '),':
        writer_end = i
        break

print(f'Writer system_template: lines {writer_start+1} to {writer_end+1}')
print(f'Current writer system_template content:')
for i in range(writer_start, writer_end+1):
    print(f'  {i+1}: {lines[i].rstrip()}')
