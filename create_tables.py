
import Dontgrade.database
import Dontgrade.models
engine = Dontgrade.database.engine
Base = Dontgrade.database.Base

if __name__ == "__main__":
    print("Creating all tables...")
    Base.metadata.create_all(bind=engine)
    print("Done.")
