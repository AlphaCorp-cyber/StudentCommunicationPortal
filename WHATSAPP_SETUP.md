# WhatsApp Quick Reply Buttons Setup Guide

This guide shows you how to set up interactive Quick Reply buttons using the latest 2025 Twilio WhatsApp API structure.

## Prerequisites

1. **Twilio Account** with WhatsApp messaging enabled
2. **WhatsApp Business Account** approved by Twilio
3. **Content Template** created in Twilio Console

## Step 1: Get Twilio Credentials

1. Go to [Twilio Console](https://console.twilio.com/)
2. Find your **Account SID** and **Auth Token**
3. Note your **WhatsApp phone number** (format: `whatsapp:+1234567890`)

## Step 2: Create Content Template

### Option A: Using Twilio Console (Recommended)
1. Go to **Messaging > Content Template Builder**
2. Click **"Create New"**
3. Select **"Quick Reply"** template type
4. Configure:
   - **Template Name**: `myinstructor_menu`
   - **Body Text**: `Welcome to myInstructor! How can I help you today?`
   - **Buttons**: 
     - Button 1: `View Lessons`
     - Button 2: `Book Lesson` 
     - Button 3: `Check Progress`
5. Submit for approval (usually takes 5-60 minutes)
6. Copy the **Content SID** (starts with `HX...`)

### Option B: Using the App (After configuring credentials)
1. Update your `.env` file with Twilio credentials
2. Visit `/test-twilio-config` in the app
3. Click **"Create Test Template"**
4. Copy the generated Content SID

## Step 3: Configure Environment Variables

Update your `.env` file:

```env
# Twilio Configuration
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=your_auth_token_here
TWILIO_PHONE_NUMBER=whatsapp:+14155238886
TWILIO_TEMPLATE_SID=HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
SESSION_SECRET=your_session_secret_here
```

## Step 4: Test the Integration

1. Restart your application
2. Visit `/test-twilio-config` to verify configuration
3. Send a test message through the WhatsApp bot interface
4. You should see interactive buttons in the actual WhatsApp conversation

## How It Works

The implementation uses three approaches in order of preference:

### 1. Content Template (Primary)
```python
message = client.messages.create(
    from_=from_number,
    to=to_number,
    content_sid="HXxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx",
    content_variables=json.dumps({
        "1": "View Lessons",
        "2": "Book Lesson", 
        "3": "Check Progress"
    })
)
```

### 2. Dynamic Template (Fallback)
Creates templates on-the-fly using the Content API

### 3. Enhanced Text (Final Fallback)
Numbered options with visual formatting

## Webhook Handling

The system processes both:
- **ButtonText**: The actual button text clicked
- **ButtonPayload**: The button ID for programmatic handling

## Troubleshooting

### Buttons Not Appearing
- ✅ Verify Twilio credentials are correct
- ✅ Check template is approved (not in pending status)
- ✅ Ensure Content SID is valid
- ✅ Test with Twilio sandbox number first

### Template Creation Fails
- Check WhatsApp Business account approval status
- Verify API permissions in Twilio Console
- Try creating template manually in Twilio Console first

### Webhook Issues
- Ensure webhook URL is publicly accessible
- Verify webhook is configured in Twilio Console
- Check Content-Type is set to `application/x-www-form-urlencoded`

## Template Variables

The template expects these content variables:
- `{1}` - First button text
- `{2}` - Second button text  
- `{3}` - Third button text

## Limitations

- Maximum 3 Quick Reply buttons per message
- Button text limited to 24 characters
- Templates require WhatsApp approval for business-initiated messages
- No approval needed for session messages (24-hour window after customer message)

## Sample Webhook Response

When user clicks a button, your webhook receives:
```
From: whatsapp:+1234567890
ButtonText: View Lessons
ButtonPayload: lessons
OriginalRepliedMessageSid: SMxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
```

The app automatically handles these responses and routes to appropriate handlers.