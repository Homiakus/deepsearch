use crate::error::AcquisitionError;
use crate::models::ArtifactReference;
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::Write;
use std::path::{Path, PathBuf};

pub struct CasArtifactWriter {
    base_dir: PathBuf,
}

impl CasArtifactWriter {
    pub fn new<P: AsRef<Path>>(base_dir: P) -> Self {
        Self {
            base_dir: base_dir.as_ref().to_path_buf(),
        }
    }

    /// Writes raw content into content-addressable storage and returns an ArtifactReference (DS-RB26).
    pub fn write_artifact(
        &self,
        data: &[u8],
        media_type: &str,
    ) -> Result<ArtifactReference, AcquisitionError> {
        let mut hasher = Sha256::new();
        hasher.update(data);
        let hash = hex::encode(hasher.finalize());

        let prefix = &hash[..2.min(hash.len())];
        let sub_dir = self.base_dir.join(prefix);
        fs::create_dir_all(&sub_dir).map_err(|e| {
            AcquisitionError::ArtifactWriteError(format!(
                "Failed to create CAS directory {:?}: {}",
                sub_dir, e
            ))
        })?;

        let extension = match media_type {
            "text/html" => "html",
            "image/png" => "png",
            "application/json" => "json",
            _ => "bin",
        };

        let file_name = format!("{}.{}", hash, extension);
        let target_path = sub_dir.join(&file_name);

        if !target_path.exists() {
            let mut file = File::create(&target_path).map_err(|e| {
                AcquisitionError::ArtifactWriteError(format!(
                    "Failed to write CAS file {:?}: {}",
                    target_path, e
                ))
            })?;
            file.write_all(data).map_err(|e| {
                AcquisitionError::ArtifactWriteError(format!("Failed to write CAS payload: {}", e))
            })?;
        }

        let uri = format!("cas://{}/{}", prefix, file_name);

        Ok(ArtifactReference {
            content_hash: hash,
            uri,
            media_type: media_type.to_string(),
            size_bytes: data.len(),
            metadata_hash: None,
        })
    }
}
