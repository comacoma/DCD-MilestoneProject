import os
from flask import Flask, redirect, render_template, request, url_for, session, flash
from flask_pymongo import PyMongo
from bson.objectid import ObjectId
from datetime import datetime
import itertools
import json

app = Flask(__name__)
app.config['SECRET_KEY'] = 'THIS_IS_SECRET_KEY'
if os.environ.get('IP') and os.environ.get('PORT'): # pragma: no cover
    app.config['MONGO_DBNAME'] = 'dcd-milestone'
    app.config['MONGO_URI'] = 'mongodb://admin:admin123@ds243041.mlab.com:43041/dcd-milestone'
else: # pragma: no cover
    app.config['MONGO_DBNAME'] = 'dcd-milestone-test'
    app.config['MONGO_URI'] = 'mongodb://admin:admin123@ds137643.mlab.com:37643/dcd-milestone-test'

mongo = PyMongo(app)

# Code from https://stackoverflow.com/questions/3744451/is-this-how-you-paginate-or-is-there-a-better-algorithm
def paginate(iterable, page_size):
    while True:
        i1, i2 = itertools.tee(iterable)
        iterable, page = (itertools.islice(i1, page_size, None),
                list(itertools.islice(i2, page_size)))
        if len(page) == 0:
            break
        yield page

def count_category(category):
    pointers = mongo.db.recipes.aggregate([{"$group": {'_id': '$'+ category, 'value':{'$sum':1}}}])
    counter = [{"label": p['_id'], "value": p['value']} for p in pointers]
    return counter

@app.route('/')
def index():
    return render_template('index.html', cuisine_count=count_category('cuisine'), origin_count=count_category('origin'))

@app.route('/login', methods=['GET',  'POST'])
def login():
    if 'username' in session:
        return redirect('/')

    if request.method == "POST":
        users = mongo.db.users
        login_user = users.find_one({'username': request.form['username']})
        if login_user and login_user['password'] == request.form['password']:
            session['username'] = request.form['username']
            return redirect('/')

        flash("Invalid username/password combination", category='error')

    return render_template('login.html')

@app.route('/register', methods=['GET',  'POST'])
def register():
    if 'username' in session:
        return redirect('/')

    if request.method == "POST":
        if request.form['username'].strip().lower() == "guest":
            flash("This is a reserved name, please choose another name.")
            return render_template('register.html')

        users = mongo.db.users
        existing_user = users.find_one({'username': request.form['username']})

        if existing_user is None:
            users.insert_one({'username': request.form['username'], 'password': request.form['password']})
            session['username'] = request.form['username']
            return redirect('/')

        flash("Username already exists!", category='error')

    return render_template('register.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    return redirect('/')

@app.route('/add_recipe')
def add_recipe():
    return render_template('add_recipe.html', cuisines=mongo.db.cuisines.find() ,countries=mongo.db.countries.find(), allergens=mongo.db.allergens.find())

@app.route('/insert_recipe', methods=['POST'])
def insert_recipe():
    recipes = mongo.db.recipes

    # Reorganise all data before inserting into database
    user_input = request.form.to_dict()

    # Separate ingredients into a separate dictionary
    ingredients = []
    unit = []
    for key, val in user_input.items():
        if 'ingredient' in key:
            ingredients.append(val.lower())
        if 'unit' in key:
            unit.append(val.lower())

    ingredients_unit = {}
    if len(ingredients) > 0 and len(unit) > 0:
        for x in range(0, len(ingredients)):
            ingredients_unit[ingredients[x]] = unit[x]

    instructions = {}
    for key, val in user_input.items():
        if 'instruction' in key:
            instructions[key] = val

    author = session['username'] if 'username' in session else 'guest'

    # Reorganise all data into one dictionary before inserting into database
    data = {
        "recipe_name": request.form['name'].lower(),
        "origin": request.form['origin'],
        "cuisine": request.form['cuisine'],
        "ingredients": ingredients_unit, # A dictionary
        "allergens": request.form.getlist('allergens'),
        "instructions": instructions, # A dictionary
        "author": author,
        "views": 0,
        "upvote": [],
        "upvote_count": 0,
        "time_created": datetime.utcnow(),
        "last_modified": datetime.utcnow()
    }

    recipes.insert_one(data)

    # Since id is auto generated and there is no way to retrieve it at this point
    # so using exact parameters user just given to find the newly created recipe and retrieve id from the record found,
    # then use the id for redirect to view_recipe.

    recipe = mongo.db.recipes.find_one({
        "recipe_name": request.form['name'],
        "origin": request.form['origin'],
        "cuisine": request.form['cuisine'],
        "ingredients": ingredients_unit, # A dictionary
        "allergens": request.form.getlist('allergens'),
        "instructions": instructions, # A dictionary
        "author": author
        })

    return redirect(url_for('view_recipe', recipe_id=recipe['_id']))

@app.route('/view_recipe/<recipe_id>')
def view_recipe(recipe_id):
    recipe = mongo.db.recipes.find_one({"_id": ObjectId(recipe_id)})
    if recipe:
        mongo.db.recipes.update_one({"_id": ObjectId(recipe_id)}, {'$inc': {"views": 1}})
        return render_template('view_recipe.html', recipe=mongo.db.recipes.find_one({"_id": ObjectId(recipe_id)}))
    else:
        flash("Invalid recipe id", category='error')
        return redirect('/')

@app.route('/edit_recipe/<recipe_id>')
def edit_recipe(recipe_id):
    recipe = mongo.db.recipes.find_one({"_id": ObjectId(recipe_id)})
    if recipe:
        # Only allows users to update recipes they created.
        if 'username' in session and session['username'] == recipe['author']:
            return render_template(
                'edit_recipe.html',
                recipe=recipe,
                cuisines=mongo.db.cuisines.find(),
                countries=mongo.db.countries.find(),
                allergens=mongo.db.allergens.find()
            )
        else:
            flash("You are not the author of that recipe, hence you are not allowed to edit.", category='error')
            return redirect('/')
    else:
        flash("Invalid recipe id", category='error')
        return redirect('/')

@app.route('/update_recipe/<recipe_id>', methods=['POST'])
def update_recipe(recipe_id):
    recipe = mongo.db.recipes.find_one({"_id": ObjectId(recipe_id)})
    if recipe:
        if 'username' in session and session['username'] == recipe['author']:
            user_input = request.form.to_dict()
            ingredients = []
            unit = []
            for key, val in user_input.items():
                if 'ingredient' in key:
                    ingredients.append(val)
                if 'unit' in key:
                    unit.append(val)

            ingredients_unit = {}
            for x in range(0, len(ingredients)):
                ingredients_unit[ingredients[x]] = unit[x]

            instructions = {}
            for key, val in user_input.items():
                if 'instruction' in key:
                    instructions[key] = val

            mongo.db.recipes.update_one({'_id': ObjectId(recipe_id)},
                { '$set': {
                            "recipe_name": request.form['name'],
                            "origin": request.form['origin'],
                            "cuisine": request.form['cuisine'],
                            "ingredients": ingredients_unit, # A dictionary
                            "allergens": request.form.getlist('allergens'),
                            "instructions": instructions,
                            "last_modified": datetime.utcnow()
                        }})

            return redirect(url_for('view_recipe', recipe_id=recipe['_id']))
        else:
            flash("You are not the author of that recipe, hence you are not allowed to edit.", category='error')
            return redirect('/')
    else:
        flash("Invalid recipe id", category='error')
        return redirect('/')

@app.route('/delete_recipe/<recipe_id>')
def delete_recipe(recipe_id):
    recipe = mongo.db.recipes.find_one({"_id": ObjectId(recipe_id)})
    if recipe:
        if 'username' in session and session['username'] == recipe['author']:
            mongo.db.recipes.delete_one({"_id": ObjectId(recipe_id)})
            return redirect(url_for('user_page', user_name=recipe['author']))
        else:
            flash("You are not the author of that recipe, hence you are not allowed to delete.", category='error')
            return redirect('/')
    else:
        flash("Invalid recipe id", category='error')
        return redirect('/')

@app.route('/upvote/<recipe_id>')
def upvote(recipe_id):
    recipe = mongo.db.recipes.find_one({"_id": ObjectId(recipe_id)})
    if recipe:
        if 'username' in session: # In order to use upvote, one need to login.
            if session['username'] not in recipe['upvote']:
                recipe['upvote'].append(session['username'])
            elif session['username'] in recipe['upvote']:
                recipe['upvote'].remove(session['username'])

            mongo.db.recipes.update_one({"_id": ObjectId(recipe_id)},
                    { '$set': {
                        "upvote": recipe['upvote'],
                        "upvote_count": len(recipe['upvote'])
                    }})

            return redirect(url_for('view_recipe', recipe_id=recipe['_id']))
        else:
            return redirect('/login')
    else:
        flash("Invalid recipe id", category='error')
        return redirect('/')

@app.route('/user/<user_name>')
def user_page(user_name):
    user = mongo.db.users.find_one({'username': user_name})
    if user and 'username' in session and user_name == session['username']:
        pointer = mongo.db.recipes.find({"author": user_name })
        recipes = [p for p in pointer]
        return render_template('user_page.html', recipes=recipes)
    elif user == None:
        flash("No such user", category='error')
        return redirect('/')
    elif 'username' not in session:
        return redirect(url_for('login'))
    elif user_name != session['username']:
        return redirect(url_for('user_page', user_name=session['username']))
    else: # pragma: no cover
        flash("An error has occured, please try again.", category='error')
        return redirect('/')

@app.route('/new_arrivals')
def new_arrivals():
    new_arrivals = mongo.db.recipes.find().sort([('time_created', -1)]).limit(15)
    return render_template('new_arrivals.html', new_arrivals=new_arrivals)

@app.route('/most_popular')
def most_popular():
    most_popular = mongo.db.recipes.find().sort([('views', -1)]).limit(15)
    return render_template('most_popular.html', most_popular=most_popular)

@app.route('/most_upvote')
def most_upvote():
    most_upvote = mongo.db.recipes.find().sort([('upvote_count', -1)]).limit(15)
    return render_template('most_upvote.html', most_upvote=most_upvote)

@app.route('/guest_recipes')
def guest_recipes():
    random_pointers = mongo.db.recipes.find({"author": 'guest' }).sort([('time_created', -1)]).limit(15)
    random = [r for r in random_pointers]
    return render_template('guest_recipes.html', random=random)

@app.route('/recipes_by_cuisine/<cuisine>/<page>')
def recipes_by_cuisine(cuisine, page):
    pointers = mongo.db.recipes.find({"cuisine": cuisine})
    recipes = list(paginate([p for p in pointers], 10))
    return render_template('recipes_by_cuisine.html', cuisine_count=count_category('cuisine'), cuisine=cuisine, recipes=recipes, page=page)

@app.route('/recipes_by_origin/<origin>/<page>')
def recipes_by_origin(origin, page):
    pointers = mongo.db.recipes.find({"origin": origin})
    recipes = list(paginate([p for p in pointers], 10))
    return render_template('recipes_by_origin.html', origin_count=count_category('origin'), origin=origin, recipes=recipes, page=page)

@app.route('/all_recipes/<page>')
def all_recipes(page):
    recipes = list(paginate(mongo.db.recipes.find().sort([('last_modified', -1)]), 10))
    return render_template('all_recipes.html', recipes=recipes, page=page)

@app.route('/custom_search', methods=['POST', 'GET'])
def custom_search():
    return render_template('custom_search.html', cuisines=mongo.db.cuisines.find() ,countries=mongo.db.countries.find(), allergens=mongo.db.allergens.find())

@app.route('/custom_search/search', methods=['POST'])
def custom_search_process():
    user_input = request.form.to_dict()
    empty_flag = { # As in if no input is given
        "name": "",
        "ingredient_1": "",
        "author": "",
    }
    if user_input == empty_flag:
        return redirect(url_for('custom_search'))
    ingredients = []
    for key, val in user_input.items():
        if 'ingredient' in key and len(val.strip()) > 0:
            ingredients.append(val)

    q = {}
    q["$and"] = []

    try:
        if len(request.form["name"].strip()) > 0:
            q["$and"].append({"recipe_name": {"$regex": ".*" + request.form['name'].strip().lower() + ".*"}})
    except: # pragma: no cover
        pass
    if len(ingredients) > 0:
        for i in ingredients:
            q["$and"].append({"ingredients."+i: {"$exists": True}})
    if len(request.form['author'].strip()) > 0:
        q["$and"].append({"author": request.form['author'].strip().lower()})
    if len(request.form.getlist('allergens')) > 0:
        q["$and"].append({"allergens": {"$all": request.form.getlist('allergens')}})
    try:
        q["$and"].append({"cuisine": request.form['cuisine']})
    except:
        pass
    try:
        q["$and"].append({"origin": request.form['origin']})
    except:
        pass

    if q != {}:
        pointers = mongo.db.recipes.find(q).sort([('last_modified', -1)])
        session['q'] = q
        return redirect(url_for('custom_search_results', page=1))

@app.route('/custom_search/results/<page>', methods=['GET'])
def custom_search_results(page):
    q = session['q']
    pointers = mongo.db.recipes.find(q).sort([('last_modified', -1)])
    results = list(paginate([p for p in pointers], 10))
    return render_template('custom_search_results.html', results=results, page=page)

if __name__ == '__main__': # pragma: no cover
    if os.environ.get('IP') and os.environ.get('PORT'):
        app.run(host=os.environ.get('IP'),
                port=int(os.environ.get('PORT')),
                debug=False, threaded=True)
    else:
        app.run(debug=True, threaded=True)
