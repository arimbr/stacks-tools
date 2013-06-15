import json, sqlite3
import time #TODO remove
from collections import deque, defaultdict

import config, general
from functions import *

def find_tag(label, label_tags):
  if not label in label_tags:
    return "ZZZZ"
  else:
    return label_tags[label]

# path to the TeX files
path = config.websiteProject + "/"
# list of TeX files
files = list_text_files(path)

labels = []
tags = get_tags(path)

# dictionary labels -> tags
label_tags = dict((tags[n][1], tags[n][0]) for n in range(0, len(tags)))

# dictionary tags -> height in graph
tags_nr = dict()
n = 0
while n < len(tags):
  tags_nr[tags[n][0]] = 0
  n = n + 1
tags_nr['ZZZZ'] = 0

# dictionary tags -> referenced tags
tags_refs = dict()
n = 0
while n < len(tags):
  tags_refs[tags[n][0]] = []
  n = n + 1
tags_refs['ZZZZ'] = []

ext = ".tex"
for name in files:
  filename = path + name + ext
  tex_file = open(filename, 'r')
  in_proof = 0
  line_nr = 0
  verbatim = 0
  next_proof = 0
  refs_proof = []

  for line in tex_file:
    # Update line number
    line_nr = line_nr + 1

    # Check for verbatim, because we do not check correctness
    # inside verbatim environment.
    verbatim = verbatim + beginning_of_verbatim(line)
    if verbatim:
      if end_of_verbatim(line):
        verbatim = 0
      continue

    # Find label if there is one
    label = find_label(line)
    if label:
      if next_proof:
        proof_label = name + "-" + label
        proof_tag = find_tag(proof_label, label_tags)

    # Reset boolean
    next_proof = 0

    # Beginning environment?
    if beginning_of_env(line):
      if proof_env(line):
        next_proof = 1

    # In proofs
    if in_proof:
      if not proof_tag == 'ZZZZ':
        refs = find_refs(line, name)
        refs_proof.extend(refs)
      if end_of_proof(line) and not proof_tag == 'ZZZZ':
        refs_proof_set = set(refs_proof)
        refs_proof_set.discard('ZZZZ')
        refs_proof = list(refs_proof_set)
        nr = -1
        tags_proof = []
        n = 0
        while n < len(refs_proof):
          ref_tag = find_tag(refs_proof[n], label_tags)
          tags_proof = tags_proof + [ref_tag]
          nr_ref = tags_nr[ref_tag]
          if nr_ref > nr:
            nr = nr_ref
          n = n + 1
        tags_nr[proof_tag] = nr + 1
        tags_refs[proof_tag] = tags_proof
        refs_proof = []
        in_proof = 0
    else:
      in_proof = beginning_of_proof(line)

  tex_file.close()

connection = sqlite3.connect(config.database)

# get names for tags from the database
names = {}
def getName(tag):
  try:
    query = "SELECT name FROM tags WHERE tag = :tag"
    cursor = connection.execute(query, [tag])

    result = cursor.fetchone()
    if result != None:
      return result[0]
    else:
      return ""

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]

def addNames():
  for tag, label in tags:
    names[tag] = getName(tag)

addNames()

# map tags to IDs
tagToID = {}

def getID(tag):
  try:
    query = "SELECT book_id FROM tags WHERE tag = ?"
    cursor = connection.execute(query, [tag])

    result = cursor.fetchone()
    if result != None:
      return result[0]
    else:
      return ""

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]

def addIDs():
  for tag, label in tags:
    tagToID[tag] = getID(tag)

addIDs()

# get sections for tags from the database
tagToSection = {}
tagToChapter = {}

sections = {}
filenameToChapter = {}

def getSectionsAndChapters():
  global sections, filenameToChapter

  try:
    query = "SELECT tags.book_id, tags.name, tags.tag, file FROM tags, sections WHERE tags.book_id = sections.number AND type = 'section'"
    cursor = connection.execute(query)

    result = cursor.fetchall()
    for section in result:
      sections[section[0]] = (section[0], section[1], section[2], section[3])
      if not "." in section[0]:
        filenameToChapter[section[3]] = section[0]

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]

getSectionsAndChapters()


def getPosition(tag):
  try:
    query = "SELECT position FROM tags WHERE tag = :tag"
    cursor = connection.execute(query, [tag])

    result = cursor.fetchone()
    if result != None:
      return result[0]
    else:
      return ""

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]

def getContainingTag(position):
  try:
    query = "SELECT tag FROM tags WHERE position < ? AND active = 'TRUE' AND type != 'item' AND TYPE != 'equation' ORDER BY position DESC LIMIT 1"
    cursor = connection.execute(query, [position])

    return cursor.fetchone()[0]

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]


def mapTagToSectionAndChapter(tag, label):
  (filename, tagType) = tuple(split_label(label)[0:2])

  # chapter is based on filename
  tagToChapter[tag] = sections[filenameToChapter[filename]]

  # section is a little harder due to items
  if tagType != "item":
    ID = tagToID[tag]
    sectionID = ".".join(ID.split(".")[0:2])
    tagToSection[tag] = sections[sectionID]
  else:
    containingTag = getContainingTag(getPosition(tag)) # we have to use the tag that contains this item
    ID = tagToID[containingTag]
    sectionID = ".".join(ID.split(".")[0:2])
    tagToSection[tag] = sections[sectionID]


def mapTags():
  for tag, label in tags:
    mapTagToSectionAndChapter(tag, label)

mapTags()

# get tag contents from database
tagContents = {}

def getTagContents(tag):
  try:
    query = "SELECT value FROM tags WHERE tag = ?"
    cursor = connection.execute(query, [tag])

    result = cursor.fetchone()
    if result != None and result[0] != None:
      tagContents[tag] = result[0]
    else:
      tagContents[tag] = ""

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]

def getAllTags():
  for tag, label in tags:
    getTagContents(tag)

def removeProof(content):
  return content.split("\\begin{proof}")[0]

# not necessary for now
#getAllTags()

# dictionary for easy label access
tags_labels = dict((v, k) for k, v in label_tags.iteritems())

# empty variables for graph creation
result = {"nodes": [], "links": []}
mapping = {}
n = 0

def updateGraph(tag, depth):
  global mapping, n, result

  if depth <= result["nodes"][mapping[tag]]["depth"]:
    return

  result["nodes"][mapping[tag]]["depth"] = depth

  for child in tags_refs[tag]:
    updateGraph(child, depth + 1)

def generateGraph(tag, depth = 0):
  global mapping, n, result

  if tag not in mapping.keys():
    mapping[tag] = n
    n = n + 1
    result["nodes"].append(
      {"tag": tag, 
       "size": tags_nr[tag],
       "file" : split_label(tags_labels[tag])[0],
       "type": split_label(tags_labels[tag])[1],
       "tagName": names[tag],
       "book_id": tagToID[tag],
       "depth": depth
       # TODO also chapter name etc, but I don't feel like it right now
      })

    for child in tags_refs[tag]:
      generateGraph(child, depth + 1)
      result["links"].append({"source": mapping[tag], "target": mapping[child]})
  else:
    # overwrite depth if necessary
    result["nodes"][mapping[tag]]["depth"] = max(depth, result["nodes"][mapping[tag]]["depth"])
    updateGraph(tag, depth)


def generateTree(tag, depth = 0, cutoff = 4):
  tagType = split_label(tags_labels[tag])[1]

  # child node
  if tags_refs[tag] == [] or depth == cutoff:
    return {
      "tag": tag,
      "type": tagType,
      "size": 2000,
      "book_id" : tagToID[tag],
      "file" : split_label(tags_labels[tag])[0],
      "tagName": names[tag],
    }
  else:
    return {
      "tag": tag,
      "type": tagType,
      "size": 2000,
      "book_id" : tagToID[tag],
      "tagName": names[tag],
      "file" : split_label(tags_labels[tag])[0],
      "children": [generateTree(child, depth + 1, cutoff) for child in set(tags_refs[tag])],
    }
        
def countTree(tree):
  if "children" not in tree.keys():
    return 1
  else:
    return 1 + sum([countTree(tag) for tag in tree["children"]])


def generatePacked(tag):
  children = set(getChildren(tag))

  packed = defaultdict(list)
  packed["tagName"] = "" # TODO fix this
  packed["nodeType"] = "root"
  packed["book_id"] = tagToID[tag]
  packed["tag"] = tag
  packed["file"] = split_label(tags_labels[tag])[0]
  packed["type"] = split_label(tags_labels[tag])[1]
  chaptersMapping = {}
  sectionsMapping = defaultdict(dict)
  for child in children:
    chapter = tagToChapter[child][1]
    section = tagToSection[child][1]

    if chapter not in chaptersMapping:
      chaptersMapping[chapter] = max(chaptersMapping.values() + [-1]) + 1
      #print "assigning " + str(chaptersMapping[chapter]) + " to " + chapter
      packed["children"].append(
        {"tagName": chapter,
         "nodeType": "chapter",
         "type": "chapter",
         "children": [],
         "book_id": tagToChapter[child][0],
         "tag": tagToChapter[child][2],
        })

    if section not in sectionsMapping[chapter]:
      sectionsMapping[chapter][section] = max(sectionsMapping[chapter].values() + [-1]) + 1
      #print "assigning " + str(sectionsMapping[chapter][section]) + " to " + chapter + ", " + section
      packed["children"][chaptersMapping[chapter]]["children"].append(
        {"tagName": section, 
         "nodeType": "section",
         "type": "section",
         "book_id": tagToSection[child][0],
         "tag": tagToSection[child][2],
         "children": []
        })

    packed["children"][chaptersMapping[chapter]]["children"][sectionsMapping[chapter][section]]["children"].append(
      {"tagName": "", # TODO fix this
       "nodeType": "tag",
       "size": 2000,
       "tag": child,
       "book_id": tagToID[child],
       "file" : split_label(tags_labels[child])[0],
       "type": split_label(tags_labels[child])[1],
      })

  return packed


# force directed dependency graph
def generateForceDirectedGraphs():
  for tag in tags:
    global mapping, n, result
    # clean data
    mapping = {}
    n = 0
    result = {"nodes": [], "links": []}
  
    f = open(config.website + "/data/" + tag[0] + "-force.json", "w")
    generateGraph(tag[0])
    print "generating " + tag[0] + "-force.json, which contains " + str(len(result["nodes"])) + " nodes and " + str(len(result["links"])) + " links"

    f.write(json.dumps(result, indent = 2))
    f.close()

# treeview (or clusterview)
maximum = 150
maximumCutoff = 6
def optimizeTree(tag):
  cutoffValue = 1
  tree = generateTree(tag, cutoff = cutoffValue)

  while True:
    candidate = generateTree(tag, cutoff = cutoffValue + 1)

    # three reasons to stop: too big a tree, all nodes reached or too deep a tree
    if countTree(candidate) > maximum or countTree(candidate) == countTree(tree) or cutoffValue >= maximumCutoff:
      return tree
    else:
      tree = candidate
      cutoffValue = cutoffValue + 1

def generateClusterGraphs():
  for tag in tags:
    f = open(config.website + "/data/" + tag[0] + "-tree.json", "w")
    #result = generateTree(tag[0], cutoff = 3)
    result = optimizeTree(tag[0])
    print "generating " + tag[0] + " which contains " + str(countTree(result)) + " nodes"
    f.write(json.dumps(result, indent = 2))
    f.close()

tagToChildren = {}

def mapChildrenToTag(tag):
  queue = deque([tag])
  result = set([])

  while queue:
    tag = queue.popleft()
    if tag not in result:
      result.add(tag)
      queue.extend(tags_refs[tag])

  return result

# we cache these results as we need them very often
def mapChildren():
  global tagToChildren
  for tag, label in tags:
    tagToChildren[tag] = mapChildrenToTag(tag)

mapChildren()

def getChildren(tag):
  global tagToChildren
  return tagToChildren[tag]



# packed view with clusters corresponding to parts and chapters
def generateCollapsibleGraphs():
  for tag in tags:
    f = open(config.website + "/data/" + tag[0] + "-packed.json", "w")
    packed = generatePacked(tag[0])
    print "generating packed view for " + tag[0]
    f.write(json.dumps(packed, indent = 2))
    f.close()


# information on 
used = set([]) 

def getEdgesCount(tag, clear = True):
  global used
  if clear:
    used = set([])

  if tag in used:
    return 0

  else:
    used.add(tag)
    return len(list(tags_refs[tag])) + sum([getEdgesCount(child, False) for child in tags_refs[tag]], 0)

def getNodesCount(tag):
  return len(getChildren(tag))

def getEdgesCountWithMultiples(tag):
  queue = deque([tag])
  result = 0

  while queue:
    tag = queue.popleft()
    result = result + 1
    queue.extend(tags_refs[tag])

  return result - 1

def getChapterCount(tag):
  return len(set([tagToChapter[child] for child in getChildren(tag)]))

def getSectionCount(tag):
  return len(set([tagToSection[child] for child in getChildren(tag)]))

def getReferencingTagsCount(tag):
  result = 0
  for candidate, label in tags:
    if tag in tags_refs[candidate]: result = result + 1

  return result

def getIndirectReferencingTagsCount(tag):
  result = 0
  for candidate, label in tags:
    if tag in getChildren(candidate): result = result + 1

  return result

# TODO move to file and call somewhere else
def clearDependencies():
  (connection, cursor) = general.connect()

  try:
    query = 'DELETE FROM dependencies'
    cursor.execute(query)

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]

  general.close(connection)

def addDependency(source, target, cursor):
  try:
    query = 'INSERT INTO dependencies (source, target) VALUES (?, ?)'
    cursor.execute(query, [source, target])

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]

def insertDependencies():
  (connection, cursor) = general.connect()

  for tag, label in tags:
    for child in tags_refs[tag]:
      addDependency(tag, child, cursor)

  general.close(connection)



# code for a scatter plot
def scatter():
  f = open(config.website + "/data/scatter.dat", "w")

  for tag, label in tags:
    edges = getEdgesCount(tag)
    nodes = getNodesCount(tag)

    f.write(str(edges) + "\t" + str(nodes) + "\t" + tag + "\n")

  f.close()

# TODO this is code duplication with statistics/counts.py, but eventually this code should be moved there anyway, then this code becomes something for statistics.general
def keyExists(key, cursor):
  try:
    query = "SELECT COUNT(*) FROM statistics WHERE key = ?"
    cursor = cursor.execute(query, [key])

    return cursor.fetchone()[0] > 0

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]
 

def update(key, value, cursor):
  try:
    if keyExists(key, cursor):
      query = 'UPDATE statistics SET value = ? WHERE key = ?'
      cursor.execute(query, [value, key])
    else:
      query = 'INSERT INTO statistics (key, value) VALUES (?, ?)'
      cursor.execute(query, [key, value])

  except sqlite3.Error, e:
    print "An error occurred:", e.args[0]
  

def updateCounts():
  (connection, cursor) = general.connect()

  for tag, label in tags:
    if tag[3] == "0": connection.commit() # TODO remove this eventually
    if tag[3] == "0": print "committed"
    print "updating " + tag
    update(tag + " node count", getNodesCount(tag), cursor)
    update(tag + " edge count", getEdgesCount(tag), cursor)
    update(tag + " total edge count", getEdgesCountWithMultiples(tag), cursor)
    update(tag + " chapter count", getChapterCount(tag), cursor)
    update(tag + " section count", getSectionCount(tag), cursor)
    update(tag + " use count", getReferencingTagsCount(tag), cursor)
    update(tag + " indirect use count", getIndirectReferencingTagsCount(tag), cursor)

  general.close(connection)

# TODO the folder stacks-website/data should be created
