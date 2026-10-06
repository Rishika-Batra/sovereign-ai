import os
from sqlalchemy import text
from app.db.database import engine, Base, SessionLocal
from app.db.models import User, ChatSession, Message, DocumentChunk, Role, AuditLog, DocumentStatus, Workspace, Agent, PendingAction
from app.core.security import get_password_hash

def init_db():
    print("Enabling pgvector extension...")
    with engine.connect() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector;"))
        conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS workspace VARCHAR DEFAULT 'general';"))
        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS ocr_confidence FLOAT;"))
        conn.execute(text("ALTER TABLE document_chunks ADD COLUMN IF NOT EXISTS chunk_source VARCHAR DEFAULT 'text';"))
        conn.execute(text("ALTER TABLE document_status ADD COLUMN IF NOT EXISTS workspace VARCHAR DEFAULT 'general';"))
        conn.execute(text("ALTER TABLE document_status ADD COLUMN IF NOT EXISTS uploader_id INTEGER REFERENCES users(id);"))
        
        # Ensure document_acl matches required schema with uniqueness constraints
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS document_acl (
                id SERIAL PRIMARY KEY,
                document_id VARCHAR NOT NULL,
                user_id INTEGER REFERENCES users(id),
                role VARCHAR,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS uq_acl_doc_user ON document_acl (document_id, user_id) WHERE user_id IS NOT NULL;
            CREATE UNIQUE INDEX IF NOT EXISTS uq_acl_doc_role ON document_acl (document_id, role) WHERE role IS NOT NULL;
            CREATE INDEX IF NOT EXISTS ix_acl_document_id ON document_acl (document_id);
        """))
        
        conn.execute(text("""
            CREATE TABLE IF NOT EXISTS pending_actions (
                id SERIAL PRIMARY KEY,
                user_id INTEGER REFERENCES users(id) NOT NULL,
                session_id INTEGER REFERENCES chat_sessions(id),
                tool VARCHAR NOT NULL,
                arguments JSON NOT NULL,
                status VARCHAR NOT NULL DEFAULT 'pending',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            );
        """))

        conn.commit()
    print("pgvector extension enabled & schema updated.")

    print("Creating tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created.")
    
    db = SessionLocal()

    # Seed roles
    default_roles = ["employee", "engineer", "admin", "manager"]
    for r_name in default_roles:
        r_obj = db.query(Role).filter(Role.name == r_name).first()
        if not r_obj:
            db.add(Role(name=r_name))
    db.commit()

    # Admin User (workspace: general)
    admin_email = "admin@sovereign.local"
    admin_user = db.query(User).filter(User.email == admin_email).first()
    if not admin_user:
        print(f"Creating admin user {admin_email}...")
        hashed_password = get_password_hash(os.getenv("SEED_ADMIN_PASSWORD", "change-me-admin"))
        admin_user = User(
            email=admin_email,
            password_hash=hashed_password,
            role="admin",
            department="IT",
            workspace="general",
        )
        db.add(admin_user)
        db.commit()
        print("Admin user created successfully.")
    else:
        # Ensure workspace is set to general if it was null
        if not admin_user.workspace:
            admin_user.workspace = "general"
        if admin_user.role != "admin":
            admin_user.role = "admin"
        db.commit()
        print("Admin user already exists.")

    # Engineer User (workspace: engineering)
    eng_email = "engineer@sovereign.local"
    eng_user = db.query(User).filter(User.email == eng_email).first()
    if not eng_user:
        print(f"Creating engineer user {eng_email}...")
        hashed_password = get_password_hash(os.getenv("SEED_ENGINEER_PASSWORD", "change-me-engineer"))
        eng_user = User(
            email=eng_email,
            password_hash=hashed_password,
            role="engineer",
            department="Engineering",
            workspace="engineering",
        )
        db.add(eng_user)
        db.commit()
        print("Engineer user created successfully.")
    else:
        if not eng_user.workspace:
            eng_user.workspace = "engineering"
        if eng_user.role != "engineer":
            print(f"Updating engineer user role to engineer...")
            eng_user.role = "engineer"
        db.commit()
        print("Engineer user already exists.")

    # Employee User (workspace: general)
    emp_email = "employee@sovereign.local"
    emp_user = db.query(User).filter(User.email == emp_email).first()
    if not emp_user:
        print(f"Creating employee user {emp_email}...")
        hashed_password = get_password_hash(os.getenv("SEED_EMPLOYEE_PASSWORD", "change-me-employee"))
        emp_user = User(
            email=emp_email,
            password_hash=hashed_password,
            role="employee",
            department="HR",
            workspace="general",
        )
        db.add(emp_user)
        db.commit()
        print("Employee user created successfully.")
    else:
        if emp_user.role != "employee":
            emp_user.role = "employee"
            db.commit()
        print("Employee user already exists.")

    # Manager User (workspace: general)
    mgr_email = "manager@sovereign.local"
    mgr_user = db.query(User).filter(User.email == mgr_email).first()
    if not mgr_user:
        print(f"Creating manager user {mgr_email}...")
        hashed_password = get_password_hash(os.getenv("SEED_MANAGER_PASSWORD", "change-me-manager"))
        mgr_user = User(
            email=mgr_email,
            password_hash=hashed_password,
            role="manager",
            department="Management",
            workspace="general",
        )
        db.add(mgr_user)
        db.commit()
        print("Manager user created successfully.")
    else:
        if not mgr_user.workspace:
            mgr_user.workspace = "general"
        if mgr_user.role != "manager":
            print(f"Updating manager user role to manager...")
            mgr_user.role = "manager"
        db.commit()
        print("Manager user already exists.")
    
    # Seed workspaces table from existing workspace strings
    existing_workspaces = set()
    for ws_name in ["general", "engineering"]:
        existing_workspaces.add(ws_name)
    # Also gather any workspaces already present in document_status or users tables
    for user_ws in db.query(User.workspace).distinct().all():
        if user_ws[0]:
            existing_workspaces.add(user_ws[0])
    for doc_ws in db.query(DocumentStatus.workspace).distinct().all():
        if doc_ws[0]:
            existing_workspaces.add(doc_ws[0])
    for ws_name in existing_workspaces:
        if not db.query(Workspace).filter(Workspace.name == ws_name).first():
            db.add(Workspace(name=ws_name))
    db.commit()
    print(f"Workspaces seeded: {sorted(existing_workspaces)}")

    # Seed Agents
    predefined_agents = [
        {
            "name": "Inspection Analyst",
            "description": "Analyzes inspection or document findings and summarizes risk level.",
            "prompt_template": "Analyze the inspection findings for {target}. Based on the component statuses and readings found, provide: (1) a summary of each component's condition, (2) an overall risk level (Low/Medium/High/Critical) with justification, and (3) a recommended next action."
        },
        {
            "name": "Approval Note Generator",
            "description": "Drafts a short approval or sign-off note summarizing a decision.",
            "prompt_template": "Draft a short approval/sign-off note summarizing the decision for {subject}."
        }
    ]
    for agent_data in predefined_agents:
        if not db.query(Agent).filter(Agent.name == agent_data["name"]).first():
            db.add(Agent(
                name=agent_data["name"],
                description=agent_data["description"],
                prompt_template=agent_data["prompt_template"],
                created_by=admin_user.id if admin_user else None
            ))
    db.commit()
    print("Agents seeded successfully.")

    db.close()

if __name__ == "__main__":
    init_db()
