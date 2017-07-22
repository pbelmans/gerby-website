from peewee import *

import os
import os.path
import logging, sys

logging.basicConfig(stream=sys.stdout)
log = logging.getLogger(__name__)
log.setLevel(logging.INFO)


PATH = "book"
db = SqliteDatabase("stacks.sqlite")

class BaseModel(Model):
  class Meta:
    database = db

class Tag(BaseModel):
  tag = CharField(unique=True, primary_key=True)
  label = CharField()
  active = BooleanField()
  ref = CharField()
  type = CharField()
  html = TextField()

class Proof(BaseModel):
  tag = ForeignKeyField(Tag, related_name = "proofs")
  html = TextField()
  number = IntegerField()

# create database if it doesn't exist already
if not os.path.isfile("stacks.sqlite"):
  db.create_tables([Tag, Proof])
  log.info("Created database")


# the information on disk
files = [f for f in os.listdir(PATH) if os.path.isfile(os.path.join(PATH, f)) and f != "index"] # index is always created
tagFiles = [filename for filename in files if filename.endswith(".tag")]
proofFiles = [filename for filename in files if filename.endswith(".proof")]

# import tags
for filename in tagFiles:
  with open(os.path.join(PATH, filename)) as f:
    value = f.read()

  filename = filename[:-4]
  pieces = filename.split("-")

  try:
    tag = Tag.get(Tag.tag == pieces[2])

    if tag.label != "-".join(pieces[3:]):
      log.info("Tag %s: label has changed", tag.tag)
    if tag.html != value:
      log.info("Tag %s: content has changed", tag.tag)
    if tag.type != pieces[0]:
      log.info("Tag %s: type has changed", tag.tag)

    Tag.update(label="-".join(pieces[3:]), ref=pieces[1], type=pieces[0], html=value).where(Tag.tag == pieces[2]).execute()

  except DoesNotExist:
    tag = Tag.create(tag=pieces[2], label="-".join(pieces[3:]), ref=pieces[1], type=pieces[0], active=True, html=value)
    log.info("Created tag %s", pieces[2])


# import proofs
for filename in proofFiles:
  with open(os.path.join(PATH, filename)) as f:
    value = f.read()

  filename = filename[:-6]
  pieces = filename.split("-")

  try:
    proof = Proof.get(Proof.tag == pieces[0], number=int(pieces[1]))

    if proof.html != value:
      log.info("Tag %s: proof #%s has changed", proof.tag.tag, pieces[1])

    Proof.update(html=value)

  except DoesNotExist:
    proof = Proof.create(tag=pieces[0], html=value, number=pieces[1])
    log.info("tag %s: created proof #%s", proof.tag.tag, proof.number)


# check (in)activity of tags
with open("tags") as f:
  tags = f.readlines()
  tags = [line.strip() for line in tags if not line.startswith("#")]
  tags = dict([line.split(",") for line in tags if "," in line])

  for tag in Tag.select():
    if tag.tag not in tags:
      Tag.update(active=False).where(Tag.tag == tag.tag)
      log.info("Tag %s became inactive", tag.tag)
    else:
      if tag.label != tags[tag.tag]:
        log.error("Labels for tag %s differ from tags file to database:\n  %s\n  %s", tag.tag, tags[tag.tag], tag.label)

