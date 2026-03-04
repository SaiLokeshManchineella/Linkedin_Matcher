from pydantic import AliasChoices, Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from langchain_openai import ChatOpenAI, OpenAIEmbeddings
from langchain_core.output_parsers import StrOutputParser
from dotenv import load_dotenv

load_dotenv()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=("../../.env", "../.env", ".env"),
        env_file_encoding="utf-8",
        populate_by_name=True,
        extra="ignore",
    )

    # API keys
    openai_api_key: str = Field("", validation_alias=AliasChoices("OPENAI_API_KEY"))
    rapidapi_key: str = Field("", validation_alias=AliasChoices("RAPIDAPI_KEY"))

    # OpenAI models
    openai_chat_model: str = Field("gpt-4o-mini", validation_alias=AliasChoices("OPENAI_CHAT_MODEL"))
    openai_embedding_model: str = Field("text-embedding-3-small", validation_alias=AliasChoices("OPENAI_EMBEDDING_MODEL"))
    openai_embedding_dimensions: int = Field(768, validation_alias=AliasChoices("OPENAI_EMBEDDING_DIMENSIONS"))

    # Qdrant
    qdrant_url: str = Field("http://localhost:6333", validation_alias=AliasChoices("QDRANT_URL"))
    qdrant_collection: str = Field("pro_tinder_clusters", validation_alias=AliasChoices("QDRANT_COLLECTION"))
    qdrant_similarity_threshold: float = Field(0.75, validation_alias=AliasChoices("QDRANT_SIMILARITY_THRESHOLD"))

    # Neo4j
    neo4j_uri: str = Field("bolt://localhost:7687", validation_alias=AliasChoices("NEO4J_URI"))
    neo4j_user: str = Field("neo4j", validation_alias=AliasChoices("NEO4J_USER"))
    neo4j_password: str = Field("password123", validation_alias=AliasChoices("NEO4J_PASSWORD"))

    # App
    app_name: str = "Pro-Tinder"


settings = Settings()  # type: ignore[call-arg]

# ---- Shared LangChain instances ----
model = ChatOpenAI(model=settings.openai_chat_model, temperature=0.35)
embeddings = OpenAIEmbeddings(model=settings.openai_embedding_model, dimensions=settings.openai_embedding_dimensions)
parser = StrOutputParser()
