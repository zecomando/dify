CREATE TABLE legal_documents (
  id UUID PRIMARY KEY,
  source TEXT NOT NULL,
  jurisdiction TEXT NOT NULL,
  document_type TEXT NOT NULL,
  title TEXT NOT NULL,
  official_citation TEXT,
  source_identifier TEXT,
  source_url TEXT NOT NULL,
  canonical_url TEXT,
  court TEXT,
  process_number TEXT,
  case_number TEXT,
  application_number TEXT,
  ecli TEXT,
  celex TEXT,
  eli TEXT,
  publication_date DATE,
  decision_date DATE,
  version_date DATE,
  effective_date DATE,
  is_current BOOLEAN DEFAULT TRUE,
  is_consolidated BOOLEAN DEFAULT FALSE,
  legal_value_warning TEXT,
  area TEXT[],
  subarea TEXT[],
  language TEXT DEFAULT 'pt',
  status TEXT DEFAULT 'raw',
  sha256 TEXT NOT NULL,
  raw_object_key TEXT,
  parsed_object_key TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_legal_documents_source ON legal_documents(source);
CREATE INDEX idx_legal_documents_jurisdiction ON legal_documents(jurisdiction);
CREATE INDEX idx_legal_documents_type ON legal_documents(document_type);
CREATE INDEX idx_legal_documents_status ON legal_documents(status);
CREATE INDEX idx_legal_documents_current ON legal_documents(is_current);
CREATE INDEX idx_legal_documents_celex ON legal_documents(celex);
CREATE INDEX idx_legal_documents_ecli ON legal_documents(ecli);
CREATE INDEX idx_legal_documents_sha256 ON legal_documents(sha256);

CREATE TABLE legal_chunks (
  id UUID PRIMARY KEY,
  document_id UUID NOT NULL REFERENCES legal_documents(id),
  chunk_type TEXT NOT NULL,
  structural_path TEXT,
  citation_label TEXT,
  article_number TEXT,
  paragraph_number TEXT,
  alineia TEXT,
  recital_number TEXT,
  section_number TEXT,
  text_content TEXT NOT NULL,
  normalized_text TEXT,
  token_count INTEGER,
  vector_id TEXT,
  sparse_id TEXT,
  metadata JSONB DEFAULT '{}',
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_legal_chunks_document_id ON legal_chunks(document_id);
CREATE INDEX idx_legal_chunks_chunk_type ON legal_chunks(chunk_type);
CREATE INDEX idx_legal_chunks_article ON legal_chunks(article_number);
CREATE INDEX idx_legal_chunks_vector_id ON legal_chunks(vector_id);

CREATE TABLE source_ingestion_jobs (
  id UUID PRIMARY KEY,
  source TEXT NOT NULL,
  source_url TEXT NOT NULL,
  requested_by TEXT,
  mode TEXT DEFAULT 'manual',
  status TEXT DEFAULT 'pending',
  error_message TEXT,
  document_id UUID REFERENCES legal_documents(id),
  started_at TIMESTAMP,
  completed_at TIMESTAMP,
  created_at TIMESTAMP DEFAULT NOW(),
  updated_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_source_ingestion_jobs_status ON source_ingestion_jobs(status);
CREATE INDEX idx_source_ingestion_jobs_source ON source_ingestion_jobs(source);

CREATE TABLE answer_audits (
  id UUID PRIMARY KEY,
  session_id TEXT,
  user_id TEXT,
  user_query TEXT NOT NULL,
  normalized_query TEXT,
  detected_area TEXT[],
  detected_jurisdiction TEXT[],
  detected_document_types TEXT[],
  mode TEXT DEFAULT 'strict',
  retrieved_chunks JSONB,
  reranked_chunks JSONB,
  evidence JSONB,
  draft_answer TEXT,
  validator_report JSONB,
  final_answer TEXT,
  confidence TEXT,
  abstained BOOLEAN DEFAULT FALSE,
  verdict TEXT,
  model_generator TEXT,
  model_validator TEXT,
  embedding_model TEXT,
  reranker_model TEXT,
  latency_ms INTEGER,
  estimated_cost_usd NUMERIC(12, 6),
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_answer_audits_session ON answer_audits(session_id);
CREATE INDEX idx_answer_audits_user ON answer_audits(user_id);
CREATE INDEX idx_answer_audits_created_at ON answer_audits(created_at);
CREATE INDEX idx_answer_audits_verdict ON answer_audits(verdict);
CREATE INDEX idx_answer_audits_abstained ON answer_audits(abstained);

CREATE TABLE user_feedback (
  id UUID PRIMARY KEY,
  answer_audit_id UUID NOT NULL REFERENCES answer_audits(id),
  user_id TEXT,
  rating TEXT NOT NULL,
  reason TEXT,
  comment TEXT,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_user_feedback_answer ON user_feedback(answer_audit_id);
CREATE INDEX idx_user_feedback_rating ON user_feedback(rating);

CREATE TABLE evaluation_runs (
  id UUID PRIMARY KEY,
  passed BOOLEAN NOT NULL,
  total_cases INTEGER NOT NULL,
  successful_cases INTEGER NOT NULL,
  failed_cases INTEGER NOT NULL,
  metrics JSONB NOT NULL,
  quality_gates JSONB NOT NULL,
  failed_cases_detail JSONB NOT NULL,
  evals_dir TEXT NOT NULL,
  created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_evaluation_runs_created_at ON evaluation_runs(created_at);
CREATE INDEX idx_evaluation_runs_passed ON evaluation_runs(passed);
