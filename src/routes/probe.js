const express = require('express');
const ffmpeg = require('fluent-ffmpeg');
const multer = require('multer');
const path = require('path');

const logger = require('../utils/logger.js');
const utils = require('../utils/utils.js');

const router = express.Router();

// Setup Multer to save file in /tmp
const storage = multer.diskStorage({
  destination: '/tmp',
  filename: (req, file, cb) => {
    const uniqueName = `${Date.now()}-${file.originalname}`;
    cb(null, uniqueName);
  }
});
const upload = multer({ storage: storage });

router.post('/', upload.single('file'), function (req, res, next) {
  const savedFile = req.file.path;

  logger.debug(`Probing ${savedFile}`);

  ffmpeg(savedFile).ffprobe(function (err, metadata) {
    // Delete temp file after probe
    utils.deleteFile(savedFile);

    if (err) {
      logger.error(err);
      return res.status(500).json({ status: 'error', message: err.message });
    }

    res.status(200).json({
      status: 'success',
      duration: metadata.format.duration,
      metadata: metadata
    });
  });
});

module.exports = router;
