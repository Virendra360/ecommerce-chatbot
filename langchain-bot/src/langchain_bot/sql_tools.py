from pathlib import Path

from langchain_community.utilities import SQLDatabase
from langchain_community.agent_toolkits import SQLDatabaseToolkit
from langchain_openai import ChatOpenAI

from dotenv import load_dotenv

load_dotenv()


def get_database():
    root = Path(__file__).resolve().parents[2]
    db_path = root / "ecommerce.db"

    return SQLDatabase.from_uri(
        f"sqlite:///{db_path}"
    )


def get_sql_tools():
    db = get_database()

    llm = ChatOpenAI(
        model="gpt-4o-mini",
        temperature=0
    )

    toolkit = SQLDatabaseToolkit(
        db=db,
        llm=llm
    )

    return toolkit.get_tools()