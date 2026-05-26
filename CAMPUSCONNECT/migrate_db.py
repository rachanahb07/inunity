"""
Database migration script for new teacher cabin location fields.
Run this once to add the new columns to the database.
"""

from app import app, db
from models import Teacher
from sqlalchemy import inspect

def migrate_database():
    """Add new cabin location columns to Teacher model"""
    with app.app_context():
        # Get table columns
        inspector = inspect(db.engine)
        teacher_columns = [col['name'] for col in inspector.get_columns('user')]
        
        # Check which columns are missing
        missing_columns = []
        for col_name in ['cabin_block', 'cabin_floor', 'cabin_room']:
            if col_name not in teacher_columns:
                missing_columns.append(col_name)
        
        if missing_columns:
            print(f"Adding missing columns: {missing_columns}")
            
            # Create new columns
            if 'cabin_block' not in teacher_columns:
                db.engine.execute('ALTER TABLE user ADD COLUMN cabin_block VARCHAR(50)')
                print("✅ Added cabin_block column")
            
            if 'cabin_floor' not in teacher_columns:
                db.engine.execute('ALTER TABLE user ADD COLUMN cabin_floor VARCHAR(50)')
                print("✅ Added cabin_floor column")
            
            if 'cabin_room' not in teacher_columns:
                db.engine.execute('ALTER TABLE user ADD COLUMN cabin_room VARCHAR(50)')
                print("✅ Added cabin_room column")
            
            print("\n✅ Database migration completed successfully!")
        else:
            print("✅ All columns already exist. No migration needed.")

if __name__ == '__main__':
    try:
        migrate_database()
    except Exception as e:
        print(f"❌ Migration failed: {e}")
        print("\nNote: If using SQLite, you may need to:")
        print("1. Delete the database.db file in the instance folder")
        print("2. Restart the app to create a fresh database with new schema")
