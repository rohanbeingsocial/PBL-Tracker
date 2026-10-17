-- 07_reference_data.sql
-- Subjects and the starting list of tags. Users and projects are loaded from
-- data/*.csv by scripts/load_data.py.
SET search_path = pbl, extensions;

-- Labs are marked out of 33. A subject with a theory paper gives its project 5.
INSERT INTO subjects (code, name, max_marks) VALUES
('DBMS-PBL', 'Database Management Systems Lab',        33),
('ML-PBL',   'Machine Learning Lab',                    33),
('IOT-PBL',  'Internet of Things Lab',                  33),
('CN-TH',    'Computer Networks (theory) mini project',  5);

-- Students can add new tags when they submit a project; these are the common ones.
INSERT INTO tags (name) VALUES
('Arduino'), ('ESP32'), ('ESP8266'), ('Raspberry Pi'), ('RFID'), ('GPS'), ('GSM'), ('LoRa'),
('MQTT'), ('Blynk'), ('ThingSpeak'), ('Node-RED'), ('Firebase'),
('Python'), ('Java'), ('PHP'), ('Flask'), ('Django'), ('React'), ('Node.js'), ('Flutter'),
('Streamlit'), ('Tkinter'),
('MySQL'), ('PostgreSQL'), ('SQLite'),
('scikit-learn'), ('XGBoost'), ('TensorFlow'), ('TensorFlow Lite'), ('OpenCV'), ('MediaPipe'),
('dlib'), ('NLTK'), ('Hugging Face Transformers'), ('SHAP');
