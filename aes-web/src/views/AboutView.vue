<template>
  <div class="about-page">
    <h1>Tentang Automated Essay Scoring</h1>
    
    <div class="card">
      <h2>Apa itu Automated Essay Scoring?</h2>
      <p>
        Automated Essay Scoring (AES) adalah sistem yang menggunakan teknologi kecerdasan buatan untuk menilai 
        jawaban esai siswa secara otomatis. Sistem ini dirancang untuk membantu guru dalam menilai jawaban 
        esai dengan lebih efisien dan konsisten, sambil memberikan umpan balik yang konstruktif kepada siswa.
      </p>
    </div>
    
    <div class="card">
      <h2>Teknologi yang Digunakan</h2>
      <div class="tech-section">
        <div class="tech-item">
          <h3>Large Language Model (LLM)</h3>
          <p>
            Sistem ini menggunakan model bahasa besar Llama-3.2 untuk memahami dan mengevaluasi jawaban esai. 
            LLM mampu memahami konteks, mengenali konsep penting, dan memberikan evaluasi yang mendalam 
            terhadap jawaban siswa.
          </p>
        </div>
        
        <div class="tech-item">
          <h3>Retrieval-Augmented Generation (RAG)</h3>
          <p>
            RAG adalah teknik yang menggabungkan kemampuan retrieval (pengambilan) informasi dengan 
            generasi teks. Sistem ini menggunakan RAG untuk mengambil konten yang relevan dari buku referensi 
            yang kemudian digunakan oleh LLM untuk mengevaluasi jawaban siswa.
          </p>
        </div>
        
        <div class="tech-item">
          <h3>BM25</h3>
          <p>
            BM25 adalah algoritma retrieval berbasis kata kunci yang digunakan untuk mengambil dokumen yang 
            relevan berdasarkan kesamaan leksikal (kata). Algoritma ini efektif untuk menemukan dokumen yang 
            mengandung kata kunci yang sama dengan query.
          </p>
        </div>
        
        <div class="tech-item">
          <h3>Dense Passage Retrieval (DPR)</h3>
          <p>
            DPR adalah metode retrieval berbasis semantik yang menggunakan embedding vektor untuk menemukan 
            dokumen yang secara makna relevan dengan query, bahkan jika tidak mengandung kata kunci yang sama. 
            DPR dapat menangkap hubungan semantik yang lebih dalam dibandingkan BM25.
          </p>
        </div>
      </div>
    </div>
    
    <div class="card">
      <h2>Cara Kerja Sistem</h2>
      <ol class="workflow">
        <li>
          <strong>Persiapan Dokumen Referensi</strong>
          <p>
            Sistem memproses buku referensi (BUKU_IPA.pdf) dan membaginya menjadi chunk-chunk kecil 
            yang dapat diindeks dan diambil.
          </p>
        </li>
        <li>
          <strong>Pengajuan Pertanyaan</strong>
          <p>
            Guru membuat pertanyaan esai yang akan dijawab oleh siswa.
          </p>
        </li>
        <li>
          <strong>Pengumpulan Jawaban</strong>
          <p>
            Siswa menjawab pertanyaan esai melalui platform.
          </p>
        </li>
        <li>
          <strong>Retrieval Konten Relevan</strong>
          <p>
            Sistem menggunakan BM25 dan DPR untuk mengambil bagian-bagian dari buku referensi yang relevan 
            dengan pertanyaan dan jawaban siswa.
          </p>
        </li>
        <li>
          <strong>Evaluasi dengan LLM</strong>
          <p>
            LLM (Llama-3.2) mengevaluasi jawaban siswa berdasarkan konten referensi yang diambil, 
            memberikan skor, mengidentifikasi kata kunci penting, memberikan alasan penilaian, 
            dan menyediakan umpan balik untuk siswa.
          </p>
        </li>
        <li>
          <strong>Penyajian Hasil</strong>
          <p>
            Hasil evaluasi ditampilkan kepada guru dan siswa, termasuk skor, evaluasi terperinci, 
            dan referensi yang digunakan.
          </p>
        </li>
      </ol>
    </div>
    
    <div class="card">
      <h2>Manfaat</h2>
      <ul class="benefits">
        <li>
          <strong>Efisiensi</strong>: Mengurangi waktu yang dibutuhkan guru untuk menilai jawaban esai.
        </li>
        <li>
          <strong>Konsistensi</strong>: Memberikan penilaian yang konsisten berdasarkan kriteria yang sama.
        </li>
        <li>
          <strong>Umpan Balik Cepat</strong>: Siswa mendapatkan umpan balik segera setelah mengirimkan jawaban.
        </li>
        <li>
          <strong>Analisis Mendalam</strong>: Memberikan analisis terperinci tentang kekuatan dan kelemahan jawaban.
        </li>
        <li>
          <strong>Transparansi</strong>: Menampilkan referensi yang digunakan untuk penilaian.
        </li>
      </ul>
    </div>
  </div>
</template>

<style scoped>
.about-page {
  max-width: 1000px;
  margin: 0 auto;
}

h1 {
  margin-bottom: 1.5rem;
  color: var(--primary-color);
}

.card {
  background-color: white;
  border-radius: 8px;
  box-shadow: 0 2px 4px rgba(0, 0, 0, 0.05);
  padding: 1.5rem;
  margin-bottom: 1.5rem;
}

h2 {
  color: var(--primary-color);
  margin-bottom: 1rem;
}

h3 {
  color: var(--secondary-color);
  margin-bottom: 0.5rem;
}

p {
  line-height: 1.6;
  margin-bottom: 1rem;
}

.tech-section {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(300px, 1fr));
  gap: 1.5rem;
  margin-top: 1rem;
}

.tech-item {
  padding: 1rem;
  border: 1px solid var(--border-color);
  border-radius: 6px;
}

.workflow {
  padding-left: 1.5rem;
  margin-top: 1rem;
}

.workflow li {
  margin-bottom: 1.5rem;
}

.workflow li strong {
  color: var(--secondary-color);
}

.benefits {
  padding-left: 1.5rem;
  margin-top: 1rem;
}

.benefits li {
  margin-bottom: 0.5rem;
}

@media (max-width: 768px) {
  .tech-section {
    grid-template-columns: 1fr;
  }
}
</style>