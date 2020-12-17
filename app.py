import os

from flask import (
    Flask,
    render_template,
    request,
    flash,
    redirect,
    session,
    g,
)
from flask_debugtoolbar import DebugToolbarExtension
from sqlalchemy.exc import IntegrityError
from forms import (
    UserAddForm,
    LoginForm,
    MessageForm,
    UserEditForm,
    UserLogoutForm,
    UserMessageLikeForm,
)
from models import db, connect_db, User, Message, UserMessage

CURR_USER_KEY = "curr_user"
DEFAULT_IMAGE_URL = "/static/images/default-pic.png"
DEFAULT_HEADER_IMAGE_URL = "/static/images/warbler-hero.jpg"

app = Flask(__name__)

# Get DB_URI from environ variable (useful for production/testing) or,
# if not set there, use development local db.
app.config['SQLALCHEMY_DATABASE_URI'] = (
    os.environ.get('DATABASE_URL', 'postgres:///warbler'))

app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SQLALCHEMY_ECHO'] = False
app.config['DEBUG_TB_INTERCEPT_REDIRECTS'] = True
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', "it's a secret")
toolbar = DebugToolbarExtension(app)

connect_db(app)


##############################################################################
# User signup/login/logout


@app.before_request
def add_user_to_g():
    """If we're logged in, add curr user to Flask global."""

    if CURR_USER_KEY in session:
        g.user = User.query.get(session[CURR_USER_KEY])

    else:
        g.user = None


def do_login(user):
    """Log in user."""

    session[CURR_USER_KEY] = user.id


def do_logout():
    """Logout user."""

    if CURR_USER_KEY in session:
        session.pop(CURR_USER_KEY, None)


@app.route('/signup', methods=["GET", "POST"])
def signup():
    """Handle user signup.

    Create new user and add to DB. Redirect to home page.

    If form not valid, present form.

    If the there already is a user with that username: flash message
    and re-present form.
    """

    form = UserAddForm()

    if form.validate_on_submit():
        try:
            user = User.signup(
                username=form.username.data,
                password=form.password.data,
                email=form.email.data,
                image_url=form.image_url.data or User.image_url.default.arg,
            )
            db.session.commit()

        except IntegrityError:
            flash("Username already taken", 'danger')
            return render_template('users/signup.html', form=form)

        do_login(user)

        return redirect("/")

    else:
        return render_template('users/signup.html', form=form)


@app.route('/login', methods=["GET", "POST"])
def login():
    """Handle user login."""

    form = LoginForm()

    if form.validate_on_submit():
        user = User.authenticate(form.username.data,
                                 form.password.data)

        if user:
            do_login(user)
            flash(f"Hello, {user.username}!", "success")
            return redirect("/")

        flash("Invalid credentials.", 'danger')

    return render_template('users/login.html', form=form)


@app.route('/logout', methods=["GET", "POST"])
def logout():
    """Handle logout of user."""

    if not g.user:
        flash("You are not logged in.", "danger")
        return redirect("/")

    form = UserLogoutForm()

    if form.validate_on_submit():
        do_logout()
        flash("You are logged out.", "success")
        return redirect("/")

    return render_template("users/logout.html", form=form)


##############################################################################
# General user routes:

@app.route('/users')
def list_users():
    """Page with listing of users.

    Can take a 'q' param in querystring to search by that username.
    """

    search = request.args.get('q')

    if not search:
        users = User.query.all()
    else:
        users = User.query.filter(User.username.ilike(f"%{search}%")).all()

    return render_template('users/index.html', users=users)


@app.route('/users/<int:user_id>')
def users_show(user_id):
    """Show user profile."""

    user = User.query.get_or_404(user_id)

    form = UserMessageLikeForm()

    return render_template('users/show.html', user=user, form=form)


@app.route('/users/<int:user_id>/following')
def show_following(user_id):
    """Show list of people this user is following."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)
    return render_template('users/following.html', user=user)


@app.route('/users/<int:user_id>/followers')
def users_followers(user_id):
    """Show list of followers of this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    user = User.query.get_or_404(user_id)
    return render_template('users/followers.html', user=user)


@app.route('/users/follow/<int:follow_id>', methods=['POST'])
def add_follow(follow_id):
    """Add a follow for the currently-logged-in user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get_or_404(follow_id)
    g.user.following.append(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.route('/users/stop-following/<int:follow_id>', methods=['POST'])
def stop_following(follow_id):
    """Have currently-logged-in-user stop following this user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    followed_user = User.query.get(follow_id)
    g.user.following.remove(followed_user)
    db.session.commit()

    return redirect(f"/users/{g.user.id}/following")


@app.route('/users/profile', methods=["GET", "POST"])
def profile():
    """Update profile for current user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    curr_username = g.user.username

    form = UserEditForm(obj=g.user)

    if form.validate_on_submit():
        if User.authenticate(curr_username, form.password.data):
            g.user.username = form.username.data
            g.user.email = form.email.data
            g.user.image_url = (
                form.image_url.data or
                DEFAULT_IMAGE_URL
            )
            g.user.header_image_url = (
                form.header_image_url.data or
                DEFAULT_HEADER_IMAGE_URL
            )
            g.user.bio = form.bio.data
            g.user.location = form.location.data
            db.session.commit()

            flash("User has been edited!", "success")
            return redirect(f"/users/{g.user.id}")
        else:
            flash("Incorrect password", "danger")
            return redirect("/")
    return render_template('users/edit.html', form=form)


@app.route('/users/delete', methods=["POST"])
def delete_user():
    """Delete user."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    do_logout()

    db.session.query(Message).filter_by(user_id=g.user.id).delete()
    db.session.flush()
    db.session.delete(g.user)
    db.session.commit()

    return redirect("/signup")


##############################################################################
# Messages routes:


@app.route('/messages/new', methods=["GET", "POST"])
def messages_add():
    """Add a message:

    Show form if GET. If valid, update message and redirect to user page.
    """

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = MessageForm()

    if form.validate_on_submit():
        msg = Message(text=form.text.data)
        g.user.messages.append(msg)
        db.session.commit()

        return redirect(f"/users/{g.user.id}")

    return render_template('messages/new.html', form=form)


@app.route('/messages/<int:message_id>', methods=["GET"])
def messages_show(message_id):
    """Show a message."""
    form = UserMessageLikeForm()

    msg = Message.query.get(message_id)
    user = User.query.get_or_404(msg.user.id)
    return render_template('messages/show.html', form=form, message=msg, user=user)


@app.route('/messages/<int:message_id>/delete', methods=["POST"])
def messages_destroy(message_id):
    """Delete a message."""

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    msg = Message.query.get(message_id)
    db.session.delete(msg)
    db.session.commit()

    return redirect(f"/users/{g.user.id}")


@app.route('/messages/liked', methods=["GET", "POST"])
def messages_liked_list():
    """ Show list of liked messages for this user """

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = UserMessageLikeForm()
    return render_template('messages/liked.html', form=form, user=g.user)


@app.route('/messages/<int:message_id>/like', methods=["POST"])
def message_like(message_id):
    """ handle message like by user """

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = UserMessageLikeForm()

    # Check if message exists
    message = Message.query.get_or_404(message_id)
    print("message =", message)

    # Check if user message, user cannot like own message
    if message.user_id == g.user.id:
        flash("Cannot like your own message", "danger")
        return redirect('/messages/liked')

    print("messages liked=", g.user.messages_liked)
    # breakpoint()
    # Check if message is not already liked
    if message not in g.user.messages_liked:
        print("message not in messages liked")
        if form.validate_on_submit():
            g.user.messages_liked.append(message)
            db.session.commit()
            print("message added to liked=", g.user.messages_liked)
            # breakpoint()
            flash("Message liked!", "success")
            return redirect('/messages/liked')

    return redirect('/messages/liked')


@app.route('/messages/<int:message_id>/unlike', methods=["POST"])
def message_unlike(message_id):
    """ handle message unlike by user """

    if not g.user:
        flash("Access unauthorized.", "danger")
        return redirect("/")

    form = UserMessageLikeForm()

    # Check if message exists
    message = Message.query.get_or_404(message_id)

    # Check if message is currently liked to unlike
    if message in g.user.messages_liked:
        if form.validate_on_submit():
            g.user.messages_liked.remove(message)
            db.session.commit()
            flash("Message unliked!", "success")
            return redirect('/messages/liked')

    return redirect('/messages/liked')

##############################################################################
# Homepage and error pages


@app.route('/')
def homepage():
    """Show homepage:

    - anon users: no messages
    - logged in: 100 most recent messages of followed_users
    """

    form = UserMessageLikeForm()

    if g.user:
        following_ids = [following.id for following in g.user.following]
        target_users = following_ids + [g.user.id]

        messages = (Message
                    .query
                    .filter(Message.user_id.in_(target_users))
                    .order_by(Message.timestamp.desc())
                    .limit(100)
                    .all())

        return render_template('home.html',
                               messages=messages,
                               user=g.user,
                               form=form,
                               )

    else:
        return render_template('home-anon.html')


##############################################################################
# Turn off all caching in Flask
#   (useful for dev; in production, this kind of stuff is typically
#   handled elsewhere)
#
# https://stackoverflow.com/questions/34066804/disabling-caching-in-flask

@app.after_request
def add_header(response):
    """Add non-caching headers on every request."""

    # https://developer.mozilla.org/en-US/docs/Web/HTTP/Headers/Cache-Control
    response.cache_control.no_store = True
    return response
