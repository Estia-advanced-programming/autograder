# Grading Process

## 1. Update student repos & build

```bash
find ../2026/pandora-2026-submissions -name pom.xml -print0 | xargs -0 -n1 dirname | sort -u | while IFS= read -r d; do (cd "$d" && git pull && mvn package); done
```

## 2. Run class_grader (produces JSON)

```bash
python3 class_grader.py -C config.yml
```

Or with explicit flags:

```bash
python3 class_grader.py -d ../2026/pandora-2026-submissions/ \
  -t ../2026/pandora-2026-the_awesome_teachers_2026/test/testSuite.json \
  -r ../2026/pandora-2026-the_awesome_teachers_2026/target/pandora.jar \
  -o reports --fast
```

Output: `reports/{teacher_eval,validation,self_eval,cross_testing,commits,coverage,groups}/`

## 3. Generate reports (reads JSON → .qmd)

```bash
python3 report_generator.py reports/
```

Output: `reports/class_report.qmd` + per-group `.qmd` files.

## 4. Render to HTML/PDF

```bash
quarto render reports/class_report.qmd
```
```