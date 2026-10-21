#!/usr/bin/env python3
"""Regenerate the fake Course Roster exports used by test_roster_import.py.

Every name, email and phone number here is invented. The layout follows the
Blackbaud Course Roster "Export Data to Excel" file: one row per student,
then a continuation row for each additional parent, and no student id column.
Needs xlwt (pip install xlwt) to write the .xls.
"""

from pathlib import Path

import xlwt

HEADER = ["Student", "Grade", "Advisor", "Parent", "Parent Email", "Parent Phone", "Address"]
FIRST = [
    ["Example, Avery Jordan '28", "10", "Teacher, A", "Pat Example", "pat@example.com",
     "555-0101", "1 Example Rd"],
    ["", "", "", "Sam Example", "sam@example.com", "555-0102", "1 Example Rd"],
    ["O'Testperson, Zoë '28", "10", "Teacher, B", "Lee O'Testperson", "lee@example.com",
     "555-0103", "2 Sample Ln"],
    ["Sample, Margaret (Maggie) '27", "11", "Teacher, A", "Kim Sample", "kim@example.com",
     "555-0104", "3 Fixture Ct"],
    ["", "", "", "Ray Sample", "ray@example.com", "555-0105", "4 Fixture Ct"],
    ["", "", "", "Jo Sample", "jo@example.com", "555-0106", "5 Fixture Ct"],
]
# The same class later in the year: one student added mid-year.
SECOND = FIRST + [
    ["Newcomer, Riley (Ri) '28", "10", "Teacher, B", "Alex Newcomer", "alex@example.com",
     "555-0107", "6 Test Way"],
]


def write(path, rows):
    book = xlwt.Workbook(encoding="utf-8")
    sheet = book.add_sheet("Course Roster")
    for c, h in enumerate(HEADER):
        sheet.write(0, c, h)
    for r, row in enumerate(rows, 1):
        for c, value in enumerate(row):
            sheet.write(r, c, value)
    book.save(str(path))


if __name__ == "__main__":
    here = Path(__file__).resolve().parent
    write(here / "course-roster.xls", FIRST)
    write(here / "course-roster-later.xls", SECOND)
