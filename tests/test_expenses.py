"""
Expense API tests — covers CRUD operations, split calculation correctness,
payment summary logic, and authorization enforcement.
"""
import pytest
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

os.environ.setdefault('DATABASE_URL', 'sqlite://')
os.environ.setdefault('POSTGRES_URL', 'sqlite://')
os.environ.setdefault('SECRET_KEY', 'test-secret-key')
os.environ.setdefault('ANTHROPIC_API_KEY', 'test-key')
os.environ.setdefault('GOOGLE_CLIENT_ID', '')

from app import app, db, User, Expense, ExpenseSplit, Payment


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture()
def client():
    """Fresh in-memory database + test client."""
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite://'
    app.config['TESTING'] = True
    with app.app_context():
        db.create_all()
        yield app.test_client()
        db.session.remove()
        db.drop_all()


@pytest.fixture()
def two_user_client(client):
    """
    Two users (A and B) in the same group.
    Returns (client_a, user_a_id, user_b_id).
    User A is the active session (group creator).
    """
    client.post('/register', data={'email': 'a@test.com', 'password': 'password123'})
    client.post('/login',    data={'email': 'a@test.com', 'password': 'password123'})
    client.post('/group', data={'action': 'create', 'name': 'Test House'})

    with app.app_context():
        user_a = User.query.filter_by(email='a@test.com').first()
        user_a_id = user_a.id
        group_code = user_a.group.code

    # Register User B and join via invite code
    other = app.test_client()
    other.post('/register', data={'email': 'b@test.com', 'password': 'password123'})
    other.post('/login',    data={'email': 'b@test.com', 'password': 'password123'})
    other.post('/group', data={'action': 'join', 'code': group_code})

    with app.app_context():
        user_b = User.query.filter_by(email='b@test.com').first()
        user_b_id = user_b.id

    return client, user_a_id, user_b_id


# =============================================================================
# HELPERS
# =============================================================================

def post_expense(client, paid_by_user_id, splits, description='Groceries',
                 amount=100.00, date='2024-06-01'):
    """POST to /api/expenses with given data."""
    return client.post('/api/expenses',
        json={
            'description': description,
            'amount': amount,
            'date': date,
            'paidByUserId': paid_by_user_id,
            'splits': splits,
        },
        content_type='application/json'
    )


def even_splits(user_ids):
    """Build equal-percentage split dicts for the given user IDs."""
    pct = round(100 / len(user_ids), 2)
    return [{'user_id': uid, 'percentage': pct} for uid in user_ids]


# =============================================================================
# EXPENSE CRUD
# =============================================================================

class TestExpenseCRUD:

    def test_create_expense_returns_201(self, two_user_client):
        """Valid expense creation should return 201 with an expenseId."""
        client, a_id, b_id = two_user_client
        resp = post_expense(client, a_id, even_splits([a_id, b_id]))
        assert resp.status_code == 201
        assert 'expenseId' in resp.get_json()

    def test_create_expense_persists_to_database(self, two_user_client):
        """The created expense should exist in the database with correct values."""
        client, a_id, b_id = two_user_client
        expense_id = post_expense(
            client, a_id, even_splits([a_id, b_id])
        ).get_json()['expenseId']

        with app.app_context():
            expense = db.session.get(Expense, expense_id)
            assert expense is not None
            assert expense.description == 'Groceries'
            assert expense.amount == 100.00
            assert expense.paid_by_user_id == a_id

    def test_create_expense_invalid_user_returns_400(self, two_user_client):
        """Passing a paidByUserId not in the group should return 400."""
        client, a_id, b_id = two_user_client
        resp = post_expense(client, paid_by_user_id=99999,
                            splits=[{'user_id': a_id, 'percentage': 100}])
        assert resp.status_code == 400

    def test_delete_expense_removes_from_database(self, two_user_client):
        """Deleting an expense should remove it from the database entirely."""
        client, a_id, b_id = two_user_client
        expense_id = post_expense(
            client, a_id, even_splits([a_id, b_id])
        ).get_json()['expenseId']

        client.delete(f'/api/expenses/{expense_id}')

        with app.app_context():
            assert db.session.get(Expense, expense_id) is None

    def test_delete_expense_cascades_to_splits(self, two_user_client):
        """Deleting an expense must also delete its associated ExpenseSplit records."""
        client, a_id, b_id = two_user_client
        expense_id = post_expense(
            client, a_id, even_splits([a_id, b_id])
        ).get_json()['expenseId']

        client.delete(f'/api/expenses/{expense_id}')

        with app.app_context():
            splits = ExpenseSplit.query.filter_by(expense_id=expense_id).all()
            assert splits == []

    def test_delete_nonexistent_expense_returns_404(self, two_user_client):
        """Attempting to delete an expense that does not exist should return 404."""
        client, a_id, b_id = two_user_client
        assert client.delete('/api/expenses/99999').status_code == 404


# =============================================================================
# SPLIT CALCULATION
# =============================================================================

class TestSplitCalculation:

    def test_even_split_amounts(self, two_user_client):
        """50/50 split on $100 should assign exactly $50 to each user."""
        client, a_id, b_id = two_user_client
        expense_id = post_expense(
            client, a_id, even_splits([a_id, b_id]), amount=100.00
        ).get_json()['expenseId']

        with app.app_context():
            splits = ExpenseSplit.query.filter_by(expense_id=expense_id).all()
            amounts = sorted([s.amount for s in splits])
            assert amounts == [50.0, 50.0]

    def test_split_amounts_sum_to_total(self, two_user_client):
        """Sum of all split amounts must equal the expense total — no rounding loss."""
        client, a_id, b_id = two_user_client
        amount = 77.50
        expense_id = post_expense(
            client, a_id, even_splits([a_id, b_id]), amount=amount
        ).get_json()['expenseId']

        with app.app_context():
            splits = ExpenseSplit.query.filter_by(expense_id=expense_id).all()
            assert round(sum(s.amount for s in splits), 2) == round(amount, 2)

    def test_custom_percentage_split(self, two_user_client):
        """70/30 split on $100 should produce $70 for A and $30 for B."""
        client, a_id, b_id = two_user_client
        expense_id = post_expense(client, a_id, splits=[
            {'user_id': a_id, 'percentage': 70},
            {'user_id': b_id, 'percentage': 30},
        ], amount=100.00).get_json()['expenseId']

        with app.app_context():
            split_map = {
                s.user_id: s.amount
                for s in ExpenseSplit.query.filter_by(expense_id=expense_id).all()
            }
            assert round(split_map[a_id], 2) == 70.00
            assert round(split_map[b_id], 2) == 30.00

    def test_split_recalculated_on_amount_update(self, two_user_client):
        """When the expense total is updated, split amounts must recalculate proportionally."""
        client, a_id, b_id = two_user_client
        expense_id = post_expense(
            client, a_id, even_splits([a_id, b_id]), amount=100.00
        ).get_json()['expenseId']

        client.put(f'/api/expenses/{expense_id}', json={
            'description': 'Groceries',
            'amount': 200.00,
            'date': '2024-06-01',
            'paidByUserId': a_id,
            'splits': even_splits([a_id, b_id])
        }, content_type='application/json')

        with app.app_context():
            splits = ExpenseSplit.query.filter_by(expense_id=expense_id).all()
            for s in splits:
                assert round(s.amount, 2) == 100.00


# =============================================================================
# PAYMENT SUMMARY
# =============================================================================

class TestPaymentSummary:

    def test_summary_zeros_when_no_expenses(self, two_user_client):
        """With no expenses, all summary values should be zero."""
        client, a_id, b_id = two_user_client
        data = client.get('/api/payments/summary').get_json()
        assert data['youOwe'] == 0.0
        assert data['youAreOwed'] == 0.0
        assert data['netBalance'] == 0.0

    def test_you_are_owed_when_you_paid(self, two_user_client):
        """When user A pays $100 split 50/50, A should be owed $50."""
        client, a_id, b_id = two_user_client
        post_expense(client, a_id, even_splits([a_id, b_id]), amount=100.00)
        data = client.get('/api/payments/summary').get_json()
        assert data['youAreOwed'] == 50.0
        assert data['youOwe'] == 0.0
        assert data['netBalance'] == 50.0

    def test_you_owe_when_someone_else_paid(self, two_user_client):
        """When user B pays $100 split 50/50, user A (active session) should owe $50."""
        client, a_id, b_id = two_user_client
        post_expense(client, b_id, even_splits([a_id, b_id]), amount=100.00)
        data = client.get('/api/payments/summary').get_json()
        assert data['youOwe'] == 50.0
        assert data['youAreOwed'] == 0.0
        assert data['netBalance'] == -50.0

    def test_completed_payment_excluded_from_summary(self, two_user_client):
        """A split covered by a completed Payment should not appear in youOwe."""
        client, a_id, b_id = two_user_client
        expense_id = post_expense(
            client, b_id, even_splits([a_id, b_id]), amount=100.00
        ).get_json()['expenseId']

        with app.app_context():
            import secrets as _secrets
            group_id = User.query.get(a_id).group_id
            db.session.add(Payment(
                user_id=a_id,
                group_id=group_id,
                expense_id=expense_id,
                amount_cents=5000,
                currency='usd',
                status='completed',
                stripe_session_id=_secrets.token_hex(16)
            ))
            db.session.commit()

        data = client.get('/api/payments/summary').get_json()
        assert data['youOwe'] == 0.0


# =============================================================================
# AUTHORIZATION
# =============================================================================

class TestExpenseAuthorization:

    def test_create_expense_no_session_returns_401(self, client):
        """Unauthenticated expense creation should be rejected with 401."""
        resp = post_expense(client, 1, [{'user_id': 1, 'percentage': 100}])
        assert resp.status_code == 401

    def test_get_expenses_no_session_returns_401(self, client):
        """Unauthenticated GET on expenses should return 401."""
        assert client.get('/api/expenses').status_code == 401

    def test_delete_expense_no_session_returns_401(self, client):
        """Unauthenticated DELETE should return 401."""
        assert client.delete('/api/expenses/1').status_code == 401

    def test_payment_summary_no_session_returns_401(self, client):
        """Unauthenticated payment summary request should return 401."""
        assert client.get('/api/payments/summary').status_code == 401
