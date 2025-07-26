const express = require('express');
const multer = require('multer');
const ffmpeg = require('fluent-ffmpeg');

const logger = require('../utils/logger.js');
const utils = require('../utils/utils.js');

const router = express.Router();

// Configure multer to save uploaded files temporarily
const upload = multer({ dest: 'uploads/' }); // adjust folder path if needed

// POST /probe - receives uploaded file, probes metadata, deletes file, returns metadata
router.post('/', upload.single('file'), function (req, res, next) {
    const savedFile = req.file?.path;

    if (!savedFile) {
        logger.error('No file uploaded in /probe request');
        return res.status(400).json({ error: 'No file uploaded.' });
    }

    logger.debug(`Probing ${savedFile}`);

    ffmpeg(savedFile).ffprobe(function (err, metadata) {
        if (err) {
            logger.error(`ffprobe failed: ${err.message}`);
            return next(err);
        }

        utils.deleteFile(savedFile); // optional cleanup
        res.status(200).json(metadata);
    });
});

module.exports = router;
