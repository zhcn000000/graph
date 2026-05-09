from knowgraph.graph.triples import CSVRowInput


class TestCSVRowInput:
    def test_csv_row_creation_minimal(self):
        row = CSVRowInput(
            object_id="OBJ-001",
            title="青铜鼎",
            museum="Metropolitan Museum of Art",
        )
        assert row.object_id == "OBJ-001"
        assert row.title == "青铜鼎"
        assert row.museum == "Metropolitan Museum of Art"
        assert row.period is None

    def test_csv_row_creation_full(self):
        row = CSVRowInput(
            object_id="OBJ-002",
            title="青花瓷瓶",
            period="明朝",
            type="瓷器",
            material="陶瓷",
            description="精美的青花瓷瓶",
            dimensions="高30cm",
            museum="Cleveland Museum of Art",
            location="Cleveland",
            detail_url="https://clevelandart.org/art/002",
            image_url="https://clevelandart.org/img/002.jpg",
            credit_line="捐赠",
            accession_number="ACC-002",
            crawl_date="2025-03-20",
        )
        assert row.type == "瓷器"
        assert row.location == "Cleveland"

    def test_to_artifact_triples_with_all_fields(self):
        row = CSVRowInput(
            object_id="OBJ-001",
            title="青铜鼎",
            period="商朝",
            type="青铜器",
            material="青铜",
            description="商朝时期的青铜鼎",
            dimensions="高50cm",
            museum="Metropolitan Museum of Art",
            location="New York",
            detail_url="https://metmuseum.org/art/001",
            image_url="https://metmuseum.org/img/001.jpg",
            credit_line="捐赠",
            accession_number="ACC-001",
        )

        triples = row.to_artifact_triples()

        assert len(triples) == 5

        triple_predicates = {t.predicate.predicate for t in triples}
        assert "collected_by" in triple_predicates
        assert "belongs_to_dynasty" in triple_predicates
        assert "made_of_material" in triple_predicates
        assert "is_type_of" in triple_predicates

        has_location = any(t.predicate.predicate == "located_at" for t in triples)
        assert has_location

    def test_to_artifact_triples_minimal(self):
        row = CSVRowInput(
            object_id="OBJ-003",
            title="山水画",
            museum="Freer Gallery of Art",
        )

        triples = row.to_artifact_triples()

        assert len(triples) == 1
        assert triples[0].predicate.predicate == "collected_by"

    def test_to_artifact_triples_no_optional_fields(self):
        row = CSVRowInput(
            object_id="OBJ-004",
            title="无名文物",
            museum="Unknown Museum",
            period=None,
            type=None,
            material=None,
            description=None,
            location=None,
        )

        triples = row.to_artifact_triples()

        assert len(triples) == 1
        assert triples[0].subject.name == "无名文物"
        assert triples[0].object.name == "Unknown Museum"

    def test_to_artifact_triples_no_location_skips_located_at(self):
        row = CSVRowInput(
            object_id="OBJ-005",
            title="Test",
            period="汉朝",
            museum="Test Museum",
            location=None,
        )

        triples = row.to_artifact_triples()

        has_location = any(t.predicate.predicate == "located_at" for t in triples)
        assert not has_location
