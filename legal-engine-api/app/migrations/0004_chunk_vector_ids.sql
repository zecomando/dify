UPDATE legal_chunk_embeddings
SET vector_id = model || ':' || chunk_id
WHERE vector_id IS NULL;

CREATE INDEX IF NOT EXISTS idx_legal_chunk_embeddings_vector_id ON legal_chunk_embeddings(vector_id);
