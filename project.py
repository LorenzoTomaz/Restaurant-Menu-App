from flask import Flask, render_template, request, redirect, jsonify, url_for, flash
from sqlalchemy import create_engine, asc
from sqlalchemy.orm import sessionmaker
from database_setup import Base, Restaurant, MenuItem, User
from flask import session as login_session
import random
import string
from oauth2client.client import flow_from_clientsecrets
from oauth2client.client import FlowExchangeError
import httplib2
import json
from flask import make_response
import requests

app = Flask(__name__)

CLIENT_ID = json.loads(
    open('client_secrets.json', 'r').read())['web']['client_id']
APPLICATION_NAME = "Restaurant Menu Application"


# Conectando com o bando de dados e criando sessão do db
engine = create_engine('sqlite:///restaurantmenuwithusers.db?check_same_thread=False')
Base.metadata.bind = engine

DBSession = sessionmaker(bind=engine)
session = DBSession()

def create_state():
    state = ''.join(
        random.choice(string.ascii_uppercase + string.digits) for x in range(32))
    login_session['state'] = state

    return state




@app.route('/gconnect', methods=['POST'])
def gconnect():
    # Validando state
    if request.args.get('state') != login_session['state']:
        response = make_response(json.dumps('state inválido.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    # obtendo código de autorização
    request.get_data()
    code = request.data.decode('utf-8')

    try:
        #criando credenciais
        oauth_flow = flow_from_clientsecrets('client_secrets.json', scope='')
        oauth_flow.redirect_uri = 'postmessage'
        credentials = oauth_flow.step2_exchange(code)
    except FlowExchangeError:
        response = make_response(
            json.dumps('Atualização do código de autorização falhou.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # checando validade do token
    access_token = credentials.access_token
    url = ('https://www.googleapis.com/oauth2/v1/tokeninfo?access_token=%s'
           % access_token)
    h = httplib2.Http()
    response = h.request(url, 'GET')[1]
    str_response = response.decode('utf-8')
    result = json.loads(str_response)

    if result.get('error') is not None:
        response = make_response(json.dumps(result.get('error')), 500)
        response.headers['Content-Type'] = 'application/json'
        return response

    # verificando se o token de acesso é valido para o usuário
    gplus_id = credentials.id_token['sub']
    if result['user_id'] != gplus_id:
        response = make_response(
            json.dumps("Token id do usuário é diferente do id do usuário."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    # verificando se o token de acesso é valido para esse aplicativo
    if result['issued_to'] != CLIENT_ID:
        response = make_response(
            json.dumps("Token id do cliente inválido para esse aplicativo."), 401)
        response.headers['Content-Type'] = 'application/json'
        return response

    stored_access_token = login_session.get('access_token')
    stored_gplus_id = login_session.get('gplus_id')
    if stored_access_token is not None and gplus_id == stored_gplus_id:
        response = make_response(json.dumps('Usuário atual ja está conectado.'),
                                 200)
        response.headers['Content-Type'] = 'application/json'
        return response

    # armazenando token de acesso na sessão do usuário.
    login_session['access_token'] = access_token
    login_session['gplus_id'] = gplus_id


    userinfo_url = "https://www.googleapis.com/oauth2/v1/userinfo"
    params = {'access_token': access_token, 'alt': 'json'}
    response = requests.get(userinfo_url, params=params)

    data = response.json()
    #armazena nome, url da foto e endereço de email a sessão do usuário
    login_session['username'] = data['name']
    login_session['picture'] = data['picture']
    login_session['email'] = data['email']

    
    user_id = getUserID(login_session['email'])
    if not user_id:
        user_id = createUser(login_session)
    login_session['user_id'] = user_id

    flash("Você está logado com %s" % login_session['email'])

    return redirect(url_for('showRestaurants'))


#função para criar usuário no db
def createUser(login_session):
    newUser = User(name=login_session['username'], email=login_session[
                   'email'], picture=login_session['picture'])
    session.add(newUser)
    session.commit()
    user = session.query(User).filter_by(email=login_session['email']).one()
    return user.id

#obtem dados do usuario salvo no db
def getUserInfo(user_id):
    user = session.query(User).filter_by(id=user_id).one()
    return user

#obtem id do usuário salvo no db
def getUserID(email):
    try:
        user = session.query(User).filter_by(email=email).one()
        return user.id
    except:
        return None


# função para desconectar usuário e limpar os dados de sessão do usuário
@app.route('/gdisconnect')
def gdisconnect():
    
    access_token = login_session.get('access_token')
    if access_token is None:
        response = make_response(
            json.dumps('Usuário atual não está conectado.'), 401)
        response.headers['Content-Type'] = 'application/json'
        return response
    url = 'https://accounts.google.com/o/oauth2/revoke?token=%s' % access_token
    h = httplib2.Http()
    result = h.request(url, 'GET')[0]
    if result['status'] == '200':
        
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']

        response = make_response(json.dumps('Sucesso ao desconectar.'), 200)
        response.headers['Content-Type'] = 'application/json'
        return response
    else:
        del login_session['access_token']
        del login_session['gplus_id']
        del login_session['username']
        del login_session['email']
        del login_session['picture']
        # Erro ao recuperar token
        response = make_response(
            json.dumps('Falha ao recuperar token para o usuário atual.'), 400)
        response.headers['Content-Type'] = 'application/json'
        return response


# API endopoint para visualizar menu de um dado restaurante com response em json
@app.route('/restaurant/<int:restaurant_id>/menu/JSON')
def restaurantMenuJSON(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    items = session.query(MenuItem).filter_by(
        restaurant_id=restaurant_id).all()
    return jsonify(MenuItems=[i.serialize for i in items])

# API endopoint para visualizar itens do menu de um dado restaurante com response em json
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/JSON')
def menuItemJSON(restaurant_id, menu_id):
    Menu_Item = session.query(MenuItem).filter_by(id=menu_id).one()
    return jsonify(Menu_Item=Menu_Item.serialize)

# API endopoint para visualizar todos os restaurantes com response em json
@app.route('/restaurant/JSON')
def restaurantsJSON():
    restaurants = session.query(Restaurant).all()
    return jsonify(restaurants=[r.serialize for r in restaurants])


# Home
@app.route('/')
@app.route('/restaurant/')
def showRestaurants():
    restaurants = session.query(Restaurant).order_by(asc(Restaurant.name))
    if 'username' not in login_session:
        state = create_state()
        print(state)
        return render_template('publicrestaurants.html', restaurants=restaurants, STATE=state)
    else:
        user =  login_session['username']
        pic = login_session['picture']
        print(pic)
        return render_template('restaurants.html', restaurants=restaurants, USER=user, PIC=pic)



# Cria um novo restaurante
@app.route('/restaurant/new/', methods=['GET', 'POST'])
def newRestaurant():
    if 'username' not in login_session:
        return redirect('/login')
    if request.method == 'POST':
        newRestaurant = Restaurant(
            name=request.form['name'], user_id=login_session['user_id'])
        session.add(newRestaurant)
        flash('Novo restaurante {} criado com sucesso'.format(newRestaurant.name))
        session.commit()
        return redirect(url_for('showRestaurants'))
    else:
        return render_template('newRestaurant.html')



# Edita um restaurante com base no usuário
@app.route('/restaurant/<int:restaurant_id>/edit/', methods=['GET', 'POST'])
def editRestaurant(restaurant_id):
    editedRestaurant = session.query(
        Restaurant).filter_by(id=restaurant_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if editedRestaurant.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert(' Você não está autorizado para editar esse restaurante. Por favor crie um restaurante para poder edita-lo.');location.href='/restaurant';}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        if request.form['name']:
            editedRestaurant.name = request.form['name']
            flash('Restaurante editado com sucesso {}'.format(editedRestaurant.name))
            return redirect(url_for('showRestaurants'))
    else:
        return render_template('editRestaurant.html', restaurant=editedRestaurant)


# Deleta um restaurante com base no usuário
@app.route('/restaurant/<int:restaurant_id>/delete/', methods=['GET', 'POST'])
def deleteRestaurant(restaurant_id):
    restaurantToDelete = session.query(
        Restaurant).filter_by(id=restaurant_id).one()
    if 'username' not in login_session:
        return redirect('/login')
    if restaurantToDelete.user_id != login_session['user_id']:
        return "<script>function myFunction() {alert('Você não está autorizado para deletar esse restaurante. Por favor crie um restaurante para poder deleta-lo.');location.href='/restaurant';}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        session.delete(restaurantToDelete)
        flash('{} Deletado com sucesso'.format(restaurantToDelete.name))
        session.commit()
        return redirect(url_for('showRestaurants', restaurant_id=restaurant_id))
    else:
        return render_template('deleteRestaurant.html', restaurant=restaurantToDelete)



# mostra o menu de um restaurante
@app.route('/restaurant/<int:restaurant_id>/')
@app.route('/restaurant/<int:restaurant_id>/menu/')
def showMenu(restaurant_id):
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    creator = getUserInfo(restaurant.user_id)
    items = session.query(MenuItem).filter_by(
        restaurant_id=restaurant_id).all()
    if 'username' not in login_session or creator.id != login_session['user_id']:
        return render_template('publicmenu.html', items=items, restaurant=restaurant, creator=creator)
    else:
        return render_template('menu.html', items=items, restaurant=restaurant, creator=creator)


# cria um item no menu de um restaurante para um certo usuário
@app.route('/restaurant/<int:restaurant_id>/menu/new/', methods=['GET', 'POST'])
def newMenuItem(restaurant_id):
    if 'username' not in login_session:
        return redirect('/login')
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if login_session['user_id'] != restaurant.user_id:
        return "<script>function myFunction() {alert('Você não está autorizado para adicionar itens a esse restaurante. Por favor crie um restaurante para poder adicionar itens.');location.href='/restaurant';}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        newItem = MenuItem(name=request.form['name'], description=request.form['description'], price=request.form[
                           'price'], course=request.form['course'], restaurant_id=restaurant_id, user_id=restaurant.user_id)
        session.add(newItem)
        session.commit()
        flash('Novo item {} adicionado com sucesso'.format(newItem.name))
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('newmenuitem.html', restaurant_id=restaurant_id)



# Edita um item no menu de um restaurante para um certo usuário
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/edit', methods=['GET', 'POST'])
def editMenuItem(restaurant_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    editedItem = session.query(MenuItem).filter_by(id=menu_id).one()
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    if login_session['user_id'] != restaurant.user_id:
        return "<script>function myFunction() {alert('Você não está autorizado para editar os itens deste restaurante. Por favor crie um restaurante para poder editar seus itens.');location.href='/restaurant';}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        if request.form['name']:
            editedItem.name = request.form['name']
        if request.form['description']:
            editedItem.description = request.form['description']
        if request.form['price']:
            editedItem.price = request.form['price']
        if request.form['course']:
            editedItem.course = request.form['course']
        session.add(editedItem)
        session.commit()
        flash('Item do menu editado com sucesso')
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('editmenuitem.html', restaurant_id=restaurant_id, menu_id=menu_id, item=editedItem)


# deleta um item no menu de um restaurante para um certo usuário
@app.route('/restaurant/<int:restaurant_id>/menu/<int:menu_id>/delete', methods=['GET', 'POST'])
def deleteMenuItem(restaurant_id, menu_id):
    if 'username' not in login_session:
        return redirect('/login')
    restaurant = session.query(Restaurant).filter_by(id=restaurant_id).one()
    itemToDelete = session.query(MenuItem).filter_by(id=menu_id).one()
    if login_session['user_id'] != restaurant.user_id:
        return "<script>function myFunction() {alert('Você não está autorizado para deletar os items deste restaurante. Por favor crie um restaurante para poder deleta seus itens.');location.href='/restaurant';}</script><body onload='myFunction()''>"
    if request.method == 'POST':
        session.delete(itemToDelete)
        session.commit()
        flash('item do menu deletado com sucesso')
        return redirect(url_for('showMenu', restaurant_id=restaurant_id))
    else:
        return render_template('deleteMenuItem.html', item=itemToDelete)


if __name__ == '__main__':
    app.secret_key = 'super_secret_key'
    app.debug = False
    app.run(host='0.0.0.0', port=5000)
