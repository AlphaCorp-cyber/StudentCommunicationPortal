from flask import Blueprint, request, jsonify
from twilio.twiml.messaging_response import MessagingResponse
from enhanced_whatsapp_bot import enhanced_bot
import logging

logger = logging.getLogger(__name__)

# Create blueprint for WhatsApp routes
whatsapp_bp = Blueprint('whatsapp', __name__, url_prefix='/whatsapp')

@whatsapp_bp.route('/webhook', methods=['POST'])
def whatsapp_webhook():
    """Handle incoming WhatsApp messages via Twilio webhook"""
    try:
        # Get message details from Twilio
        incoming_msg = request.values.get('Body', '').strip()
        from_number = request.values.get('From', '').replace('whatsapp:', '')
        media_url = request.values.get('MediaUrl0')  # First media attachment
        
        logger.info(f"Received WhatsApp message from {from_number}: {incoming_msg}")
        
        # Process message through enhanced bot
        response_text = enhanced_bot.process_message(from_number, incoming_msg, media_url)
        
        # Create Twilio response
        resp = MessagingResponse()
        resp.message(response_text)
        
        logger.info(f"Sent WhatsApp response to {from_number}: {response_text}")
        
        return str(resp)
        
    except Exception as e:
        logger.error(f"Error in WhatsApp webhook: {str(e)}")
        resp = MessagingResponse()
        resp.message("Sorry, I'm having technical difficulties. Please try again later.")
        return str(resp)

@whatsapp_bp.route('/send', methods=['POST'])
def send_whatsapp_message():
    """API endpoint to send WhatsApp messages"""
    try:
        data = request.get_json()
        phone_number = data.get('phone_number')
        message = data.get('message')
        
        if not phone_number or not message:
            return jsonify({'error': 'phone_number and message are required'}), 400
        
        success = enhanced_bot.send_whatsapp_message(phone_number, message)
        
        if success:
            return jsonify({'status': 'sent', 'message': 'Message sent successfully'})
        else:
            return jsonify({'status': 'error', 'message': 'Failed to send message'}), 500
            
    except Exception as e:
        logger.error(f"Error sending WhatsApp message: {str(e)}")
        return jsonify({'error': str(e)}), 500

@whatsapp_bp.route('/status', methods=['GET'])
def whatsapp_status():
    """Check WhatsApp bot status"""
    try:
        return jsonify({
            'status': 'active',
            'twilio_configured': enhanced_bot.twilio_client is not None,
            'phone_number': enhanced_bot.twilio_phone,
            'bot_version': 'Enhanced Multi-Role Bot v2.0'
        })
    except Exception as e:
        return jsonify({'error': str(e)}), 500