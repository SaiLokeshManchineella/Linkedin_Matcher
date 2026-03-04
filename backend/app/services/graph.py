import hashlib
from typing import List, Dict, Any
from neo4j import GraphDatabase
from config import settings


class GraphService:
    def __init__(self) -> None:
        self.driver = GraphDatabase.driver(
            settings.neo4j_uri,
            auth=(settings.neo4j_user, settings.neo4j_password),
        )
        self._ensure_indexes()

    def close(self) -> None:
        self.driver.close()

    # ---- Setup ----

    def _ensure_indexes(self) -> None:
        """Create constraints and indexes for query performance."""
        statements = [
            "CREATE CONSTRAINT user_url IF NOT EXISTS FOR (u:User) REQUIRE u.linkedin_url IS UNIQUE",
            "CREATE INDEX topic_name IF NOT EXISTS FOR (t:Topic) ON (t.name)",
            "CREATE INDEX category_id IF NOT EXISTS FOR (c:Category) ON (c.id)",
        ]
        with self.driver.session() as session:
            for stmt in statements:
                try:
                    session.run(stmt)
                except Exception:
                    pass  # constraint/index may already exist on older Neo4j

    # ---- Write ----

    @staticmethod
    def _deterministic_category_id(topics: List[str]) -> str:
        """Hash sorted topics to produce a stable category ID.
        Users with the same set of topics share a Category node.
        """
        key = "|".join(sorted(t.strip().lower() for t in topics if t.strip()))
        return hashlib.sha256(key.encode("utf-8")).hexdigest()[:16]

    def write_user_graph(
        self,
        linkedin_url: str,
        full_name: str,
        headline: str,
        profile_image_url: str,
        topics: List[str],
        reasoning: str,
    ) -> None:
        """Write / update a user node, its category, and topic links.

        - User is MERGEd by linkedin_url (stable identity).
        - Category is MERGEd by a deterministic hash of sorted topics,
          so users with identical topic sets share a Category.
        - Old topic edges are removed before writing new ones to keep
          the graph accurate on re-submissions.
        """
        category_id = self._deterministic_category_id(topics)

        query = (
            # Upsert User by linkedin_url
            "MERGE (u:User {linkedin_url: $linkedin_url}) "
            "SET u.full_name = $full_name, "
            "    u.headline = $headline, "
            "    u.profile_image_url = $profile_image_url "

            # Remove stale topic / category edges on re-submission
            "WITH u "
            "OPTIONAL MATCH (u)-[old_t:INTERESTED_IN]->() DELETE old_t "
            "WITH u "
            "OPTIONAL MATCH (u)-[old_c:IN_CATEGORY]->() DELETE old_c "

            # Upsert Category by deterministic ID
            "WITH u "
            "MERGE (c:Category {id: $category_id}) "
            "SET c.reasoning = $reasoning "
            "MERGE (u)-[:IN_CATEGORY]->(c) "

            # Create topic links
            "WITH u "
            "UNWIND $topics AS t "
            "MERGE (topic:Topic {name: t}) "
            "MERGE (u)-[:INTERESTED_IN]->(topic) "
        )

        with self.driver.session() as session:
            session.run(
                query,
                linkedin_url=linkedin_url,
                full_name=full_name,
                headline=headline,
                profile_image_url=profile_image_url,
                category_id=category_id,
                topics=topics,
                reasoning=reasoning,
            )

    # ---- Read (GraphRAG) ----

    def find_similar_by_topics(
        self,
        linkedin_url: str,
        limit: int = 10,
    ) -> List[Dict[str, Any]]:
        """Find users who share the most Topic nodes with the given user.

        Returns a list sorted by number of shared topics (descending).
        Each entry contains profile metadata, shared topic count, shared
        topic names, and a normalised similarity score (shared / max_topics).
        """
        query = (
            "MATCH (me:User {linkedin_url: $url})-[:INTERESTED_IN]->(t:Topic) "
            "WITH me, COLLECT(t) AS my_topics, COUNT(t) AS my_count "
            "UNWIND my_topics AS t "
            "MATCH (other:User)-[:INTERESTED_IN]->(t) "
            "WHERE other.linkedin_url <> $url "
            "WITH other, COUNT(t) AS shared, COLLECT(t.name) AS shared_topics, my_count "
            "ORDER BY shared DESC "
            "LIMIT $limit "
            "RETURN other.linkedin_url  AS linkedin_url, "
            "       other.full_name     AS fullName, "
            "       other.headline      AS headline, "
            "       other.profile_image_url AS profile_image_url, "
            "       shared, "
            "       shared_topics, "
            "       my_count"
        )

        with self.driver.session() as session:
            result = session.run(query, url=linkedin_url, limit=limit)
            matches: List[Dict[str, Any]] = []
            for record in result:
                my_count = record["my_count"] or 1
                shared = record["shared"] or 0
                matches.append({
                    "linkedin_url": record["linkedin_url"] or "",
                    "fullName": record["fullName"] or "",
                    "headline": record["headline"] or "",
                    "profile_image_url": record["profile_image_url"] or "",
                    "similarity": round(shared / max(my_count, 1), 4),
                    "topics": record["shared_topics"] or [],
                    "source": "graph",
                    "shared_topic_count": shared,
                })
            return matches