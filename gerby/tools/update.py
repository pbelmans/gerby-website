import re
import os
import os.path
import logging, sys
import pickle
import pybtex.database
import subprocess
import collections

from PyPDF2 import PdfFileReader

from gerby.database import *
import gerby.configuration

db.init(gerby.configuration.DATABASE)

logging.basicConfig(stream=sys.stdout)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)

# create database if it doesn't exist already
if not os.path.isfile(gerby.configuration.DATABASE):
  for model in [Tag, Proof, Slogan, History, Reference]:
    model.create_table()
  log.info("Created database")

if not os.path.isfile("comments.sqlite"):
  Comment.create_table()

# the information on disk
files = [f for f in os.listdir(gerby.configuration.PATH) if os.path.isfile(os.path.join(gerby.configuration.PATH, f)) and f != "index"] # index is always created

tagFiles = [filename for filename in files if filename.endswith(".tag")]
proofFiles = [filename for filename in files if filename.endswith(".proof")]
footnoteFiles = [filename for filename in files if filename.endswith(".footnote")]
# TODO make sure that plasTeX copies the used .bib files to the output folder
bibliographyFiles = [filename for filename in files if filename.endswith(".bib")]

extras = ("slogan", "history", "reference")
extraFiles = [filename for filename in files if filename.endswith(extras)]

context = pickle.load(open(os.path.join(gerby.configuration.PAUX), "rb"))

with open(gerby.configuration.TAGS) as f:
  tags = f.readlines()
  tags = [line.strip() for line in tags if not line.startswith("#")]
  tags = dict([line.split(",") for line in tags if "," in line])
  labels = {item: key for key, item in tags.items()}


# import tags
log.info("Importing tags")
for filename in tagFiles:
  with open(os.path.join(gerby.configuration.PATH, filename)) as f:
    value = f.read()

  filename = filename[:-4]
  pieces = filename.split("-")

  # Ensure that tags are always stored with letters uppercase.
  tag, created = Tag.get_or_create(tag=pieces[2].upper())

  if created:
    log.info("  Created tag %s", pieces[2])
  else:
    if tag.label != "-".join(pieces[3:]):
      log.info("  Tag %s: label has changed", tag.tag)
    if tag.html != value:
      log.info("  Tag %s: content has changed", tag.tag)
    if tag.type != pieces[0]:
      log.info("  Tag %s: type has changed", tag.tag)

  tag.label = "-".join(pieces[3:])
  tag.ref = pieces[1]
  tag.type = pieces[0]
  tag.html = value

  tag.save()


# post-processing tags
for entity in list(Tag.select()) + list(Proof.select()):
  regex = re.compile(r'\\ref\{([0-9A-Za-z\-]+)\}')
  for label in regex.findall(entity.html):
    try:
      reference = Tag.get(Tag.label == label)
      entity.html = entity.html.replace("\\ref{" + label + "}", reference.tag)

    # if the label isn't recognised (which happens on 02BZ in the Stacks project, for a very silly reason), just ignore
    except:
      pass

  entity.save()


# import proofs
log.info("Importing proofs")
for filename in proofFiles:
  with open(os.path.join(gerby.configuration.PATH, filename)) as f:
    value = f.read()

  filename = filename[:-6]
  pieces = filename.split("-")

  proof, created = Proof.get_or_create(tag=pieces[0], number=int(pieces[1]))

  if created:
    log.info("  Tag %s: created proof #%s", proof.tag.tag, proof.number)
  else:
    if proof.html != value:
      log.info("Tag %s: proof #%s has changed", proof.tag.tag, pieces[1])

  proof.html = value

  # looking for stray \ref's
  regex = re.compile(r'\\ref\{([0-9A-Za-z\-]+)\}')
  for label in regex.findall(proof.html):
    try:
      reference = Tag.get(Tag.label == label)
      proof.html = proof.html.replace("\\ref{" + label + "}", reference.tag)

    # if the label isn't recognised (which happens on 02BZ in the Stacks project, for a very silly reason), just ignore
    except:
      pass

  proof.save()


# import footnotes
log.info("Importing footnotes")
if Footnote.table_exists():
  Footnote.drop_table()
Footnote.create_table()

for filename in footnoteFiles:
  with open(os.path.join(gerby.configuration.PATH, filename)) as f:
    value = f.read()

  label = filename.split(".")[0]

  Footnote.create(label=label, html=value)

# create search table
log.info("Populating the search tables")
if SearchTag.table_exists():
  SearchTag.drop_table()
SearchTag.create_table()

if SearchStatement.table_exists():
  SearchStatement.drop_table()
SearchStatement.create_table()

for tag in Tag.select():
  proofs = Proof.select().where(Proof.tag == tag.tag).order_by(Proof.number)
  SearchTag.insert({SearchTag.tag: tag.tag, SearchTag.html: tag.html + "".join([proof.html for proof in proofs])}).execute()

  if tag.type in ["definition", "example", "exercise", "lemma", "proposition", "remark", "remarks", "situation", "theorem"]:
    SearchStatement.insert({SearchStatement.tag: tag.tag, SearchStatement.html: tag.html}).execute()


# link chapters to parts
log.info("Assigning chapters to parts")
if Part.table_exists():
  Part.drop_table()
Part.create_table()

with open(os.path.join(gerby.configuration.PATH, "parts.json")) as f:
  parts = json.load(f)
  for part in parts:
    for chapter in parts[part]:
      Part.create(part=Tag.get(Tag.type == "part", Tag.ref == part), chapter=Tag.get(Tag.type == "chapter", Tag.ref == chapter))


# check (in)activity of tags
log.info("Checking inactivity")
for tag in Tag.select():
  if tag.tag not in tags:
    log.info("  Tag %s became inactive", tag.tag)
    tag.active = False
  else:
    if tag.label != tags[tag.tag]:
      log.error("  Labels for tag %s differ from tags file to database:\n  - %s\n  - %s", tag.tag, tags[tag.tag], tag.label)
    else:
      tag.active = True

  tag.save()


# create dependency data
log.info("Creating dependency data")
if Dependency.table_exists():
  Dependency.drop_table()
Dependency.create_table()

for proof in Proof.select():
  regex = re.compile(r'\"/tag/([0-9A-Z]{4})\"')
  with db.atomic():
    dependencies = regex.findall(proof.html)

    if len(dependencies) > 0:
      Dependency.insert_many([{"tag": proof.tag.tag, "to": to} for to in dependencies]).execute()


# import history, slogans, etc
log.info("Importing history, slogans, etc.")
for filename in extraFiles:
  with open(os.path.join(gerby.configuration.PATH, filename)) as f:
    value = f.read()

  pieces = filename.split(".")

  extras = {"slogan": Slogan, "history": History, "reference": Reference}
  for extra in extras:
    if pieces[1] == extra:
      row, created = extras[extra].get_or_create(tag=pieces[0])
      if created:
        log.info("  Tag %s: added a %s", row.tag.tag, extra)
      elif row.html != value:
        log.info("  Tag %s: %s has changed", extra, row.tag.tag)


      row.html = value
      row.save()

# import names of labels
log.info("Importing names of tags")
names = list()

for key, item in context["Gerby"].items():
  if "title" in item and key in labels:
    names.append({"tag" : labels[key], "name" : item["title"]})

for entry in names:
  Tag.update(name=entry["name"]).where(Tag.tag == entry["tag"]).execute()

# import bibliography
log.info("Importing bibliography")
if BibliographyEntry.table_exists():
  BibliographyEntry.drop_table()
BibliographyEntry.create_table()

if BibliographyField.table_exists():
  BibliographyField.drop_table()
BibliographyField.create_table()

for bibliographyFile in bibliographyFiles:
  bibtex = pybtex.database.parse_file(os.path.join(gerby.configuration.PATH, bibliographyFile))

  for key in bibtex.entries:
    entry = bibtex.entries[key]

    data = pybtex.database.BibliographyData({key: entry}) # we create a new object to output a single entry
    BibliographyEntry.create(entrytype = entry.type, key = entry.key, code = data.to_string("bibtex"))

    for field in list(entry.rich_fields.keys()) + entry.persons.keys():
      value = entry.rich_fields[field].render_as("html")

      BibliographyField.create(key = entry.key, field = field.lower(), value = value)

# managing citations
if Citation.table_exists():
  Citation.drop_table()
Citation.create_table()

for tag in Tag.select():
  regex = re.compile(r'\"/bibliography/([0-9A-Za-z\-\_]+)\"')

  with db.atomic():
    citations = regex.findall(tag.html)
    citations = list(set(citations)) # make sure citations are inserted only once

    if len(citations) > 0:
      Citation.insert_many([{"tag": tag.tag, "key": citation} for citation in citations]).execute()


# do statistics
log.info("Computing statistics")
if TagStatistic.table_exists():
  TagStatistic.drop_table()
TagStatistic.create_table()

# helper function
flatten = lambda l: [item for sublist in l for item in sublist]

# let's load the entire database in a dictionary
dependencies = collections.defaultdict(list)
for dependency in Dependency.select().dicts():
  dependencies[dependency["tag"]].append(dependency["to"])

# let's load the chapters and sections in a dictionary
chapters = dict()
sections = dict()
for tag in Tag.select():
  chapters[tag.tag] = tag.ref.split(".")[0]
  sections[tag.tag] = tag.ref.split(".")[0]
  if len(tag.ref.split(".")) >= 2:
    sections[tag.tag] = ".".join([tag.ref.split(".")[0], tag.ref.split(".")[1]])

# all the tags in the dependency graphs
preliminaries = collections.defaultdict(set)

log.info("  Processing tags for statistics")
for tag in Tag.select():
  new = dependencies[tag.tag]

  while len(new) > 0:
    preliminaries[tag.tag].update(new)

    # only include dependencies which are not yet in the set of dependencies
    new = set(flatten([dependencies[result] for result in new]))
    new = new - preliminaries[tag.tag]

log.info("  Saving statistics")
for tag in Tag.select():
  TagStatistic.create(tag=tag, statistic="preliminaries", value=len(preliminaries[tag.tag]))
  TagStatistic.create(tag=tag, statistic="chapters", value=len(set([chapters[result] for result in preliminaries[tag.tag]])))
  TagStatistic.create(tag=tag, statistic="sections", value=len(set([sections[result] for result in preliminaries[tag.tag] if len(sections[result].split(".")) == 2])))
  TagStatistic.create(tag=tag, statistic="consequences", value=sum([1 for result in preliminaries if tag.tag in preliminaries[result]]))

log.info("  Processing book statistics.")
if BookStatistic.table_exists():
  BookStatistic.drop_table()
BookStatistic.create_table()

# load book statistics computed from raw TeX code
with open(os.path.join(gerby.configuration.PATH, "meta.statistics")) as f:
  book_stats = json.load(f)
  for stat, stat_value in book_stats.items():
    BookStatistic.create(statistic=stat, value=stat_value)

# try to get pdf page counts
# currently assume that the pdf document is with the HTML
PATH_TO_BOOK_PDF = os.path.join(gerby.configuration.PATH, "book.pdf")
try:
  book_pdf = PdfFileReader(open(PATH_TO_BOOK_PDF, "rb"))
  BookStatistic.create(statistic="pages", value=book_pdf.getNumPages())
except:
  log.warning("  Unable to get page numbers")
