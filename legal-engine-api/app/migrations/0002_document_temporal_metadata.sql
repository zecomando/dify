CREATE INDEX IF NOT EXISTS idx_legal_documents_source_url_current ON legal_documents(source_url, is_current);
CREATE INDEX IF NOT EXISTS idx_legal_documents_validity ON legal_documents(valid_from, valid_until);
CREATE INDEX IF NOT EXISTS idx_legal_documents_supersedes ON legal_documents(supersedes_document_id);
