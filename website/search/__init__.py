from flask import Blueprint, render_template, abort, redirect, request, g, url_for, appcontext_pushed

import gettext

from contextlib import contextmanager

from ..parts import repo
from os import makedirs, environ
from os.path import exists, join
from shutil import rmtree
from ..translation import languages, trans_dir

from flask_wtf import Form
from wtforms import TextField
from wtforms.validators import DataRequired

import whoosh
import whoosh.fields, whoosh.index
from whoosh.analysis import LanguageAnalyzer
from whoosh.query import *
from whoosh.qparser import QueryParser, MultifieldParser
from whoosh.writing import AsyncWriter

search = Blueprint("search",__name__,template_folder="templates",static_folder="static",url_prefix='/<any(%s):lang_code>/search' % ",".join(languages))

whoosh_dir = join(environ["OPENSHIFT_DATA_DIR"],'index')
rmtree(whoosh_dir)
makedirs(whoosh_dir)

fields = {
	"facet" : whoosh.fields.ID(stored=True),
	"category" : whoosh.fields.ID(stored=True)
}

for lang in languages:
	fields["title_%s" % lang] = whoosh.fields.TEXT(stored=True,analyzer=LanguageAnalyzer(lang))
	fields["content_%s" % lang] = whoosh.fields.TEXT(stored=True,analyzer=LanguageAnalyzer(lang))
	fields["url_%s" % lang] = whoosh.fields.ID(stored=True)

schema = whoosh.fields.Schema(**fields)
index = whoosh.index.create_in(whoosh_dir, schema)
parsers = {}
for lang in languages:
    parsers[lang] = MultifieldParser(['title_%s' % lang,'content_%s' % lang],schema = index.schema)

@search.url_defaults
def add_language_code(endpoint, values):
	values.setdefault('lang_code',g.lang_code)

@search.url_value_preprocessor
def pull_language_code(endpoint, values):
	g.lang_code = values.pop('lang_code')

@contextmanager
def lang_set(app, lang):
    def handler(sender, **kwargs):
        g.lang_code = lang
    with appcontext_pushed.connected_to(handler, app):
        yield

def rebuild_index(app):
	trans = {}
	for lang in languages:
		trans[lang] = gettext.translation('parts',trans_dir,languages=[lang], fallback=True)
	with index.writer() as writer:
		for coll, in repo.itercollections():
			doc = {
				"facet" : u"parts",
				"category" : u"collection"
			}
			for lang in languages:
				with lang_set(app,lang):
					with app.app_context() as c:
						doc["title_%s" % lang] = trans[lang].ugettext(coll.name),
						doc["content_%s" % lang] = trans[lang].ugettext(coll.description)
						doc["url_%s" % lang] = unicode(url_for('parts.collection',id=coll.id))
			writer.add_document(**doc)

class SearchForm(Form):
    query = TextField("query",validators=[DataRequired()])

@search.route("/",methods=('GET','POST'))
def search_page():
    results = None
    query = request.args.get('q','')
    form = SearchForm()

    if query == '':
        if form.validate_on_submit():
            return redirect(url_for('search.search_page',q=form.query.data))
    else:
	results = []
	with index.searcher() as searcher:
		hits = searcher.search(parsers[g.lang_code].parse(query))
		for i in range(hits.scored_length()):
		    results.append({
			'title' : hits[i]['title_%s' % g.lang_code][0],
			'content' : hits[i]['content_%s' % g.lang_code][0],
			'url' : hits[i]['url_%s' % g.lang_code],
			'facet' : hits[i]['facet'],
			'category' : hits[i]['category']
		    })
    page = {'title' : 'Search'}
    return render_template('search.html', page=page,form=form,query=query,results=results)

