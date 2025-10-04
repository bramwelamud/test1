import pandas as pd
import numpy as np
import json
import csv
import os
from datetime import datetime
from fpdf import FPDF, XPos, YPos
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders
import uuid
from flask import Flask, request, jsonify
import io

class RemoteHomeCheckScorer:
    def __init__(self, smtp_config=None, data_dir="data"):
        # Questions structure matching the configuration schema from document
        self.questions = [
            { 
                "name": "fall_risk", 
                "label": "Fall Risk Assessment", 
                "options": ["Low", "Moderate", "High"] 
            },
            { 
                "name": "medication_adherence", 
                "label": "Medication Adherence", 
                "options": ["Excellent (95-100%)", "Good (80-94%)", "Fair (65-79%)", "Poor (Below 65%)"] 
            },
            { 
                "name": "cognitive_function", 
                "label": "Cognitive Function Score", 
                "options": ["Normal (26-30)", "Mild Impairment (21-25)", "Moderate Impairment (10-20)", "Severe Impairment (0-9)"] 
            },
            { 
                "name": "uti_risk", 
                "label": "UTI Risk Factors", 
                "options": ["Low Risk", "Moderate Risk", "High Risk"] 
            },
            { 
                "name": "balance_test", 
                "label": "Balance Test Result", 
                "options": ["Excellent (45-56 seconds)", "Good (35-44 seconds)", "Fair (25-34 seconds)", "Poor (Below 25 seconds)"] 
            },
            { 
                "name": "driving_safety", 
                "label": "Driving Safety Status", 
                "options": ["Safe Driver", "Minor Concerns", "Major Concerns", "Unsafe to Drive"] 
            },
            { 
                "name": "nighttime_movement", 
                "label": "Nighttime Movement Patterns", 
                "options": ["Normal Patterns", "Slightly Increased", "Significantly Increased", "Concerning Patterns"] 
            },
            { 
                "name": "social_engagement", 
                "label": "Social Engagement Level", 
                "options": ["Highly Engaged", "Moderately Engaged", "Minimally Engaged", "Socially Isolated"] 
            },
            { 
                "name": "toilet_flush_count", 
                "label": "Daily Toilet Flush Count", 
                "options": ["Normal (6-8 times)", "Slightly Elevated (9-12 times)", "Elevated (13-16 times)", "Very High (17+ times)"] 
            }
        ]
        
        # Initialize scores - Fresh base scores for each assessment
        self.base_physical_score = 100
        self.base_mental_score = 100
        
        # SMTP configuration for email - FIXED: Use provided config or environment variables
        if smtp_config is None:
            # Fallback to environment variables if no config provided
            smtp_config = {
                "server": os.environ.get('SMTP_SERVER', ''),
                "port": int(os.environ.get('SMTP_PORT', '587')),
                "username": os.environ.get('SMTP_USERNAME', ''),
                "password": os.environ.get('SMTP_PASSWORD', '')
            }
        self.smtp_config = smtp_config
        
        # Debug SMTP configuration
        print("SMTP Configuration:")
        print(f"   Server: {self.smtp_config.get('server', 'NOT SET')}")
        print(f"   Port: {self.smtp_config.get('port', 'NOT SET')}")
        print(f"   Username: {self.smtp_config.get('username', 'NOT SET')}")
        print(f"   Password: {'SET' if self.smtp_config.get('password') else 'NOT SET'}")
        
        # Data directory
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        os.makedirs(f"{data_dir}/assessments", exist_ok=True)
        os.makedirs(f"{data_dir}/reports", exist_ok=True)
        
        # Event impact mapping updated to match the new schema values
        self.event_impacts = {
            "fall_risk": {
                "Low": {"physical": 0, "mental": 0},
                "Moderate": {"physical": -3, "mental": 0},
                "High": {"physical": -8, "mental": 0}
            },
            "medication_adherence": {
                "Excellent (95-100%)": {"physical": 0, "mental": 0},
                "Good (80-94%)": {"physical": 0, "mental": 0},
                "Fair (65-79%)": {"physical": -1, "mental": -1},
                "Poor (Below 65%)": {"physical": -2, "mental": -2}
            },
            "cognitive_function": {
                "Normal (26-30)": {"physical": 0, "mental": 0},
                "Mild Impairment (21-25)": {"physical": 0, "mental": -1},
                "Moderate Impairment (10-20)": {"physical": 0, "mental": -3},
                "Severe Impairment (0-9)": {"physical": 0, "mental": -5}
            },
            "uti_risk": {
                "Low Risk": {"physical": 0, "mental": 0},
                "Moderate Risk": {"physical": -2, "mental": 0},
                "High Risk": {"physical": -4, "mental": 0}
            },
            "balance_test": {
                "Excellent (45-56 seconds)": {"physical": 0, "mental": 0},
                "Good (35-44 seconds)": {"physical": 0, "mental": 0},
                "Fair (25-34 seconds)": {"physical": -1, "mental": 0},
                "Poor (Below 25 seconds)": {"physical": -2, "mental": 0}
            },
            "driving_safety": {
                "Safe Driver": {"physical": 0, "mental": 0},
                "Minor Concerns": {"physical": -1, "mental": 0},
                "Major Concerns": {"physical": -2, "mental": 0},
                "Unsafe to Drive": {"physical": -3, "mental": 0}
            },
            "nighttime_movement": {
                "Normal Patterns": {"physical": 0, "mental": 0},
                "Slightly Increased": {"physical": 0, "mental": 0},
                "Significantly Increased": {"physical": -1, "mental": -1},
                "Concerning Patterns": {"physical": -2, "mental": -2}
            },
            "social_engagement": {
                "Highly Engaged": {"physical": 0, "mental": 0},
                "Moderately Engaged": {"physical": 0, "mental": 0},
                "Minimally Engaged": {"physical": 0, "mental": -2},
                "Socially Isolated": {"physical": 0, "mental": -4}
            },
            "toilet_flush_count": {
                "Normal (6-8 times)": {"physical": 0, "mental": 0},
                "Slightly Elevated (9-12 times)": {"physical": 0, "mental": 0},
                "Elevated (13-16 times)": {"physical": -1, "mental": 0},
                "Very High (17+ times)": {"physical": -2, "mental": 0}
            }
        }

    def validate_assessment_json(self, assessment_data):
        """Validate the assessment JSON structure"""
        errors = []
        
        # Check required fields
        required_fields = ["timestamp", "patient", "responses"]
        for field in required_fields:
            if field not in assessment_data:
                errors.append(f"Missing required field: {field}")
        
        # Check patient field
        if "patient" in assessment_data:
            patient = assessment_data["patient"]
            if not isinstance(patient, dict):
                errors.append("Patient field must be a dictionary")
            elif "email" not in patient:
                errors.append("Missing patient email")
        
        # Check responses
        if "responses" in assessment_data:
            responses = assessment_data["responses"]
            if not isinstance(responses, dict):
                errors.append("Responses field must be a dictionary")
            else:
                valid_responses, response_errors = self.validate_responses(responses)
                errors.extend(response_errors)
        
        return errors

    def validate_responses(self, responses):
        """Validate that all responses are valid options"""
        valid_responses = {}
        errors = []
        
        for question in self.questions:
            q_name = question['name']
            if q_name not in responses:
                errors.append(f"Missing response for {q_name}")
                continue
                
            response = responses[q_name]
            if response not in question['options']:
                errors.append(f"Invalid response '{response}' for {q_name}")
                continue
                
            valid_responses[q_name] = response
            
        return valid_responses, errors

    def calculate_scores(self, responses):
        """Calculate physical, mental, and insight scores based on responses"""
        # Use fresh base scores for each calculation
        physical_score = self.base_physical_score
        mental_score = self.base_mental_score
        physical_delta = 0
        mental_delta = 0
        
        # Calculate deltas based on responses
        for question_name, response in responses.items():
            if question_name in self.event_impacts and response in self.event_impacts[question_name]:
                impact = self.event_impacts[question_name][response]
                physical_delta += impact["physical"]
                mental_delta += impact["mental"]
        
        # Apply deltas (ensuring scores don't go below 0 or above 100)
        physical_score = max(0, min(100, physical_score + physical_delta))
        mental_score = max(0, min(100, mental_score + mental_delta))
        insight_score = round(0.6 * physical_score + 0.4 * mental_score, 1)
        
        return {
            "physical_score": physical_score,
            "mental_score": mental_score,
            "insight_score": insight_score,
            "tier": self.get_insight_tier(insight_score),
            "physical_delta": physical_delta,
            "mental_delta": mental_delta
        }

    def get_insight_tier(self, score):
        """Determine the insight tier based on the score"""
        if score >= 90:
            return "Independent"
        elif score >= 70:
            return "Monitor"
        elif score >= 50:
            return "Assist"
        else:
            return "Intervene"

    def get_care_plan_suggestion(self, tier, previous_tier=None):
        """Get care plan suggestions based on the insight tier"""
        suggestions = {
            "Independent": "Resume standard monitoring; schedule motivational check-in and goal-setting session",
            "Monitor": "Conduct comprehensive medication reconciliation; recommend a daytime activity or exercise program",
            "Assist": "Arrange part-time home-care aide (e.g., 12h/week); review medication-adherence log",
            "Intervene": "Recommend car-key removal; seek a senior-living community or arrange for a full-time in-home provider; enrol in fall-prevention PT"
        }
        
        if previous_tier and tier != previous_tier:
            if tier == "Monitor" and previous_tier == "Independent":
                return "Schedule balance & home-safety assessment; brief caregiver check-in"
            elif tier == "Assist" and previous_tier in ["Independent", "Monitor"]:
                return "Initiate physical-therapy evaluation; schedule telehealth PCP visit within 72h"
            elif tier == "Intervene":
                return "Convene multidisciplinary care conference (PCP, PT/OT, social worker); consider long-term-care placement"
        
        return suggestions.get(tier, "No specific recommendation")

    def save_assessment_json(self, assessment_data, scores):
        """Save the complete assessment data as JSON"""
        assessment_id = str(uuid.uuid4())
        filename = f"{self.data_dir}/assessments/{assessment_id}.json"
        
        # Create a copy to avoid modifying the original data
        data_to_save = assessment_data.copy()
        data_to_save["assessment_id"] = assessment_id
        data_to_save["scores"] = scores
        data_to_save["processed_at"] = datetime.now().isoformat()
        
        # Save to JSON file
        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(data_to_save, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"Error saving JSON file: {e}")
            raise
        
        return filename

    def save_to_csv(self, assessment_data, scores, filename=None):
        """Save assessment data to CSV file"""
        assessment_id = str(uuid.uuid4())
        if filename is None:
            filename = f"{self.data_dir}/assessments/{assessment_id}.csv"
        
        # Prepare data for CSV
        patient_data = assessment_data.get("patient", {})
        data = {
            "assessment_id": assessment_id,
            "timestamp": assessment_data.get("timestamp", ""),
            "processed_at": datetime.now().isoformat(),
            "email": patient_data.get("email", ""),
            "name": patient_data.get("name", ""),
            "age": patient_data.get("age", ""),
            "gender": patient_data.get("gender", ""),
            "physical_score": scores["physical_score"],
            "mental_score": scores["mental_score"],
            "insight_score": scores["insight_score"],
            "tier": scores["tier"],
            "physical_delta": scores["physical_delta"],
            "mental_delta": scores["mental_delta"]
        }
        
        # Add responses to data
        responses = assessment_data.get("responses", {})
        for question in self.questions:
            q_name = question['name']
            data[q_name] = responses.get(q_name, "")
        
        # Check if master CSV file exists, if not create it with headers
        master_csv_path = f"{self.data_dir}/all_assessments.csv"
        file_exists = os.path.isfile(master_csv_path)
        
        # Write to individual CSV
        try:
            with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
                fieldnames = list(data.keys())
                writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
                
                writer.writeheader()
                writer.writerow(data)
        except Exception as e:
            print(f"Error saving CSV file: {e}")
            raise
        
        # Append to master CSV file
        try:
            with open(master_csv_path, 'a', newline='', encoding='utf-8') as master_csv:
                writer = csv.DictWriter(master_csv, fieldnames=fieldnames)
                if not file_exists:
                    writer.writeheader()
                writer.writerow(data)
        except Exception as e:
            print(f"Error appending to master CSV: {e}")
        
        return filename

    def generate_pdf_in_memory(self, assessment_data, scores):
        """Generate PDF in memory for Fly.io compatibility - FIXED deprecated parameter"""
        try:
            patient = assessment_data.get("patient", {})
            responses = assessment_data.get("responses", {})
            
            pdf = FPDF()
            pdf.add_page()
            
            # Set margins to ensure proper spacing
            pdf.set_margins(20, 20, 20)
            pdf.set_auto_page_break(auto=True, margin=15)
            
            # Title
            pdf.set_font("Helvetica", 'B', 16)
            pdf.cell(0, 10, "Remote Home Check Assessment Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.ln(10)
            
            # Patient information
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(0, 10, f"Patient: {patient.get('name', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Email: {patient.get('email', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Age: {patient.get('age', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Assessment Date: {assessment_data.get('timestamp', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Previous Tier: {patient.get('previous_tier', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(10)
            
            # Scores
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "Assessment Scores", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)
            pdf.cell(0, 10, f"Physical Health Score: {scores['physical_score']:.1f}/100", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Mental Health Score: {scores['mental_score']:.1f}/100", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Insight Score: {scores['insight_score']:.1f}/100", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Tier: {scores['tier']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(10)
            
            # Risk factors
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "Assessment Responses", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)
            
            for question in self.questions:
                response = responses.get(question['name'], 'Not answered')
                text = f"{question['label']}: {response}"
                pdf.multi_cell(0, 8, text)
                pdf.ln(2)
            
            pdf.ln(10)
            
            # Care plan suggestion
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "Care Plan Suggestion", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)
            suggestion = self.get_care_plan_suggestion(scores['tier'], patient.get('previous_tier'))
            pdf.multi_cell(0, 8, suggestion)
            
            # FIXED: Use BytesIO to get PDF as bytes without deprecated 'dest' parameter
            pdf_buffer = io.BytesIO()
            pdf_output = pdf.output()  # This returns bytes in newer versions
            pdf_buffer.write(pdf_output)
            pdf_bytes = pdf_buffer.getvalue()
            pdf_buffer.close()
            
            print(f"PDF generated in memory ({len(pdf_bytes)} bytes)")
            return pdf_bytes
            
        except Exception as e:
            print(f"Error generating PDF in memory: {e}")
            return None

    def send_email(self, to_email, subject, body, assessment_data=None, scores=None):
        """Send an email with optional attachments - FIXED for Fly.io"""
        print(f"Attempting to send email to: {to_email}")
        
        # Check if SMTP is properly configured
        if not self.smtp_config or not all([self.smtp_config.get("server"), 
                                          self.smtp_config.get("port"),
                                          self.smtp_config.get("username"),
                                          self.smtp_config.get("password")]):
            print("SMTP not configured. Missing configuration:")
            if not self.smtp_config.get("server"): print("   - SMTP_SERVER")
            if not self.smtp_config.get("port"): print("   - SMTP_PORT")
            if not self.smtp_config.get("username"): print("   - SMTP_USERNAME")
            if not self.smtp_config.get("password"): print("   - SMTP_PASSWORD")
            print("Email would be sent to:", to_email)
            print("Subject:", subject)
            return False
            
        try:
            print(f"SMTP configured, sending email via {self.smtp_config['server']}:{self.smtp_config['port']}")
            
            msg = MIMEMultipart()
            msg['From'] = self.smtp_config["username"]
            msg['To'] = to_email
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain'))
            
            # Generate PDF in memory and attach it
            if assessment_data and scores:
                pdf_bytes = self.generate_pdf_in_memory(assessment_data, scores)
                if pdf_bytes:
                    part = MIMEBase('application', 'octet-stream')
                    part.set_payload(pdf_bytes)
                    encoders.encode_base64(part)
                    part.add_header(
                        'Content-Disposition',
                        'attachment; filename="health_assessment_report.pdf"'
                    )
                    msg.attach(part)
                    print("PDF generated in memory and attached")
            
            server = smtplib.SMTP(self.smtp_config["server"], self.smtp_config["port"])
            server.starttls()
            server.login(self.smtp_config["username"], self.smtp_config["password"])
            text = msg.as_string()
            server.sendmail(self.smtp_config["username"], to_email, text)
            server.quit()
            
            print(f"Email sent successfully to {to_email}")
            return True
        except Exception as e:
            print(f"Error sending email: {e}")
            return False

    def process_assessment(self, assessment_data):
        """Process a complete assessment from JSON data"""
        try:
            # Validate the assessment JSON
            errors = self.validate_assessment_json(assessment_data)
            if errors:
                return {"error": "Invalid assessment data", "details": errors}
            
            # Extract data
            patient = assessment_data.get("patient", {})
            email = patient.get("email")
            previous_tier = patient.get("previous_tier")
            responses = assessment_data.get("responses", {})
            
            # Validate responses
            valid_responses, response_errors = self.validate_responses(responses)
            if response_errors:
                return {"error": "Invalid responses", "details": response_errors}
            
            # Calculate scores
            scores = self.calculate_scores(valid_responses)
            
            # Save assessment data
            json_file = self.save_assessment_json(assessment_data, scores)
            csv_file = self.save_to_csv(assessment_data, scores)
            
            # Generate PDF (still save locally for backup, but use in-memory for email)
            pdf_file = self.generate_pdf(assessment_data, scores)
            
            # Send email with in-memory PDF attachment
            subject = "Remote Home Check Assessment Results"
            body = f"""Dear {patient.get('name', 'User')},

Your Remote Home Check assessment has been completed.

Scores:
- Physical Health: {scores['physical_score']:.1f}/100
- Mental Health: {scores['mental_score']:.1f}/100
- Insight Score: {scores['insight_score']:.1f}/100
- Tier: {scores['tier']}
- Previous Tier: {previous_tier or 'N/A'}

Care Plan Suggestion:
{self.get_care_plan_suggestion(scores['tier'], previous_tier)}

Please see the attached PDF for detailed results.

Best regards,
Remote Home Check Team
"""
            
            email_sent = self.send_email(email, subject, body, assessment_data, scores)
            
            return {
                "success": True,
                "email_sent": email_sent,
                "assessment_id": assessment_data.get("assessment_id"),
                "scores": scores,
                "pdf_file": pdf_file
            }
        
        except Exception as e:
            return {"error": "Processing failed", "details": str(e)}

    def generate_pdf(self, assessment_data, scores, filename=None):
        """Generate a PDF report for the assessment - kept for local saving"""
        if filename is None:
            assessment_id = assessment_data.get("assessment_id", str(uuid.uuid4()))
            filename = f"{self.data_dir}/reports/{assessment_id}.pdf"
        
        patient = assessment_data.get("patient", {})
        responses = assessment_data.get("responses", {})
        
        try:
            pdf = FPDF()
            pdf.add_page()
            
            # Set margins to ensure proper spacing
            pdf.set_margins(20, 20, 20)
            pdf.set_auto_page_break(auto=True, margin=15)
            
            # Title
            pdf.set_font("Helvetica", 'B', 16)
            pdf.cell(0, 10, "Remote Home Check Assessment Report", new_x=XPos.LMARGIN, new_y=YPos.NEXT, align='C')
            pdf.ln(10)
            
            # Patient information
            pdf.set_font("Helvetica", 'B', 12)
            pdf.cell(0, 10, f"Patient: {patient.get('name', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Email: {patient.get('email', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Age: {patient.get('age', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Assessment Date: {assessment_data.get('timestamp', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Previous Tier: {patient.get('previous_tier', 'N/A')}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(10)
            
            # Scores
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "Assessment Scores", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)
            pdf.cell(0, 10, f"Physical Health Score: {scores['physical_score']:.1f}/100", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Mental Health Score: {scores['mental_score']:.1f}/100", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Insight Score: {scores['insight_score']:.1f}/100", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.cell(0, 10, f"Tier: {scores['tier']}", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.ln(10)
            
            # Risk factors
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "Assessment Responses", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)
            
            for question in self.questions:
                response = responses.get(question['name'], 'Not answered')
                text = f"{question['label']}: {response}"
                pdf.multi_cell(0, 8, text)
                pdf.ln(2)
            
            pdf.ln(10)
            
            # Care plan suggestion
            pdf.set_font("Helvetica", 'B', 14)
            pdf.cell(0, 10, "Care Plan Suggestion", new_x=XPos.LMARGIN, new_y=YPos.NEXT)
            pdf.set_font("Helvetica", '', 12)
            suggestion = self.get_care_plan_suggestion(scores['tier'], patient.get('previous_tier'))
            pdf.multi_cell(0, 8, suggestion)
            
            pdf.output(filename)
        except Exception as e:
            print(f"Error generating PDF: {e}")
            raise
        
        return filename


# Initialize with SMTP configuration from environment variables
smtp_config = {
    "server": os.environ.get('SMTP_SERVER', 'smtp.mandrillapp.com'),
    "port": int(os.environ.get('SMTP_PORT', '587')),
    "username": os.environ.get('SMTP_USERNAME', 'Remote Home Check'),
    "password": os.environ.get('SMTP_PASSWORD', 'md-BvYTr9v9RGNaPTZNXm926w')
}

app = Flask(__name__)
scorer = RemoteHomeCheckScorer(smtp_config=smtp_config)

@app.route('/health', methods=['GET'])
def health_check():
    """Health check endpoint"""
    return jsonify({"status": "healthy", "message": "Remote Home Check Scorer is running"})

@app.route('/check-smtp', methods=['GET'])
def check_smtp():
    """Check SMTP configuration"""
    smtp_status = {
        "smtp_configured": bool(scorer.smtp_config and scorer.smtp_config.get("server") and scorer.smtp_config.get("username") and scorer.smtp_config.get("password")),
        "smtp_server": scorer.smtp_config.get("server", "NOT SET"),
        "smtp_port": scorer.smtp_config.get("port", "NOT SET"),
        "smtp_username": scorer.smtp_config.get("username", "NOT SET"),
        "smtp_password_set": bool(scorer.smtp_config.get("password"))
    }
    return jsonify(smtp_status)

@app.route('/assess', methods=['POST'])
def assess():
    """Endpoint to process assessment data"""
    try:
        # Get JSON data from request
        assessment_data = request.get_json()
        
        if not assessment_data:
            return jsonify({"error": "No JSON data provided"}), 400
        
        # Process the assessment
        result = scorer.process_assessment(assessment_data)
        
        if "error" in result:
            return jsonify(result), 400
        
        # Return success response
        return jsonify({
            "success": True,
            "assessment_id": result["assessment_id"],
            "scores": result["scores"],
            "email_sent": result["email_sent"]
        }), 200
        
    except Exception as e:
        return jsonify({"error": "Internal server error", "details": str(e)}), 500

@app.route('/questions', methods=['GET'])
def get_questions():
    """Endpoint to get the list of questions"""
    return jsonify(scorer.questions), 200

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host='0.0.0.0', port=port)
