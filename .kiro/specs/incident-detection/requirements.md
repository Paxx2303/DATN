# Requirements Document - Incident Detection

## Introduction

The Incident Detection feature extends the existing fisheye traffic monitoring system to automatically detect and classify traffic incidents in real-time. This system leverages existing object detection (YOLOv11), speed estimation, and congestion detection capabilities to identify various incident types including accidents, stopped vehicles, wrong-way driving, fallen objects, pedestrians in dangerous zones, and unusual traffic patterns. The system provides real-time alerts, incident lifecycle tracking, video clip extraction, and integration with emergency services.

## Glossary

- **Incident_Detector**: Core system that analyzes traffic data to identify incidents
- **Accident_Analyzer**: Component that detects vehicle collisions based on sudden stops and proximity
- **Stopped_Vehicle_Detector**: Component that identifies vehicles stationary for extended periods
- **Wrong_Way_Detector**: Component that identifies vehicles moving against expected traffic flow
- **Fallen_Object_Detector**: Component that detects stationary objects in roadway areas
- **Pedestrian_Zone_Monitor**: Component that detects pedestrians in dangerous road zones
- **Traffic_Pattern_Analyzer**: Component that identifies unusual traffic behaviors
- **Incident_Lifecycle_Manager**: System that tracks incident states from detection to resolution
- **Confidence_Scorer**: System that calculates incident confidence to reduce false positives
- **Video_Clip_Extractor**: System that extracts video segments around incident timestamps
- **Emergency_Service_Notifier**: System that sends incident data to external emergency services
- **Incident_Severity_Classifier**: System that assigns severity levels to detected incidents
- **Incident_Database**: Storage system for incident records and analytics
- **Alert_Dispatcher**: System that sends incident notifications through multiple channels
- **Geo_Incident_Mapper**: System that maps incidents to geographic locations
- **Historical_Incident_Analyzer**: System that analyzes incident patterns over time
- **Sensitivity_Config_Manager**: System that manages detection sensitivity per incident type
- **Frame_Buffer**: Circular buffer storing recent video frames for clip extraction
- **Object_Tracker**: System that tracks objects across frames using existing speed estimator
- **ROI_Manager**: System that defines regions of interest for incident detection

## Requirements

### Requirement 1: Accident Detection

**User Story:** As a traffic monitoring operator, I want to detect vehicle collisions automatically, so that emergency services can be dispatched immediately.

#### Acceptance Criteria

1. WHEN two or more vehicles are detected within 2 meters and both show sudden speed reduction to below 5 km/h within 2 seconds, THE Accident_Analyzer SHALL classify this as a potential collision
2. THE Accident_Analyzer SHALL calculate collision confidence score based on speed change magnitude, proximity duration, and vehicle orientations
3. WHEN collision confidence exceeds 0.75, THE Accident_Analyzer SHALL generate a collision incident with severity classification
4. THE Accident_Analyzer SHALL track vehicle trajectories for 5 seconds before potential collision to confirm impact
5. THE Accident_Analyzer SHALL distinguish between collision and normal traffic stop by analyzing deceleration patterns
6. WHEN a collision is detected, THE Accident_Analyzer SHALL identify all involved vehicles by class and tracking ID
7. THE Accident_Analyzer SHALL mark collision location using normalized coordinates within camera frame

### Requirement 2: Stopped Vehicle Detection

**User Story:** As a traffic monitoring operator, I want to identify vehicles that have stopped on the roadway, so that breakdowns and emergency stops can be addressed quickly.

#### Acceptance Criteria

1. WHEN a vehicle remains stationary for more than 30 seconds in a non-parking zone, THE Stopped_Vehicle_Detector SHALL generate a stopped vehicle incident
2. THE Stopped_Vehicle_Detector SHALL distinguish between stopped vehicles in traffic queues and isolated stopped vehicles
3. THE Stopped_Vehicle_Detector SHALL calculate stopped duration with 1-second accuracy
4. WHEN a stopped vehicle is detected, THE Stopped_Vehicle_Detector SHALL classify severity based on location (shoulder vs active lane)
5. THE Stopped_Vehicle_Detector SHALL track vehicle position stability to confirm it is truly stopped versus slow-moving
6. THE Stopped_Vehicle_Detector SHALL exclude vehicles in designated stopping zones from incident generation
7. WHEN a stopped vehicle resumes movement above 10 km/h, THE Stopped_Vehicle_Detector SHALL mark the incident as resolved

### Requirement 3: Wrong-Way Driving Detection

**User Story:** As a traffic safety officer, I want to detect vehicles driving against traffic flow, so that dangerous wrong-way situations can be prevented.

#### Acceptance Criteria

1. THE Wrong_Way_Detector SHALL define expected traffic flow directions for each camera ROI
2. WHEN a vehicle moves in the opposite direction to expected flow for more than 3 seconds, THE Wrong_Way_Detector SHALL generate a wrong-way incident
3. THE Wrong_Way_Detector SHALL calculate vehicle heading angle relative to expected flow direction
4. WHEN heading angle deviates by more than 135 degrees from expected direction, THE Wrong_Way_Detector SHALL classify as wrong-way movement
5. THE Wrong_Way_Detector SHALL track vehicle trajectory over at least 10 meters to confirm wrong-way behavior
6. THE Wrong_Way_Detector SHALL assign critical severity to all wrong-way incidents
7. THE Wrong_Way_Detector SHALL exclude reversing vehicles in parking areas from wrong-way detection

### Requirement 4: Fallen Object Detection

**User Story:** As a traffic monitoring operator, I want to detect debris and fallen objects on the roadway, so that hazards can be cleared before causing accidents.

#### Acceptance Criteria

1. WHEN an object appears in the roadway and remains stationary for more than 10 seconds without being classified as a vehicle or pedestrian, THE Fallen_Object_Detector SHALL generate a fallen object incident
2. THE Fallen_Object_Detector SHALL distinguish between fallen objects and road infrastructure (signs, barriers)
3. THE Fallen_Object_Detector SHALL calculate object size in square meters using camera calibration
4. WHEN object size exceeds 0.5 square meters, THE Fallen_Object_Detector SHALL classify severity as moderate or higher
5. THE Fallen_Object_Detector SHALL track object position stability to confirm it is not a moving vehicle
6. THE Fallen_Object_Detector SHALL detect cargo spills by identifying multiple small objects appearing simultaneously
7. THE Fallen_Object_Detector SHALL exclude shadows and lighting artifacts using temporal consistency checks

### Requirement 5: Pedestrian in Dangerous Zone Detection

**User Story:** As a traffic safety officer, I want to detect pedestrians in dangerous road zones, so that accidents involving pedestrians can be prevented.

#### Acceptance Criteria

1. THE Pedestrian_Zone_Monitor SHALL define dangerous zones as active traffic lanes excluding crosswalks and sidewalks
2. WHEN a pedestrian is detected in a dangerous zone for more than 2 seconds, THE Pedestrian_Zone_Monitor SHALL generate a pedestrian danger incident
3. THE Pedestrian_Zone_Monitor SHALL calculate proximity to moving vehicles within 5 meters
4. WHEN a pedestrian is within 3 meters of a vehicle moving faster than 20 km/h, THE Pedestrian_Zone_Monitor SHALL classify severity as critical
5. THE Pedestrian_Zone_Monitor SHALL track pedestrian movement direction to predict collision risk
6. THE Pedestrian_Zone_Monitor SHALL exclude pedestrians in designated crossing areas during crossing signals
7. THE Pedestrian_Zone_Monitor SHALL detect groups of pedestrians and adjust danger assessment accordingly

### Requirement 6: Unusual Traffic Pattern Detection

**User Story:** As a traffic analyst, I want to detect unusual traffic patterns like sudden slowdowns and erratic movement, so that emerging incidents can be identified early.

#### Acceptance Criteria

1. THE Traffic_Pattern_Analyzer SHALL establish baseline traffic patterns for each camera based on 7 days of historical data
2. WHEN average traffic speed drops by more than 40% within 30 seconds, THE Traffic_Pattern_Analyzer SHALL generate a sudden slowdown incident
3. THE Traffic_Pattern_Analyzer SHALL detect erratic movement when vehicle trajectory shows more than 3 direction changes within 5 seconds
4. THE Traffic_Pattern_Analyzer SHALL identify unusual density increases when vehicle count exceeds baseline by 50% within 2 minutes
5. THE Traffic_Pattern_Analyzer SHALL detect stop-and-go patterns indicating upstream incidents
6. THE Traffic_Pattern_Analyzer SHALL calculate pattern anomaly scores using statistical deviation from baseline
7. WHEN anomaly score exceeds 2.5 standard deviations, THE Traffic_Pattern_Analyzer SHALL generate an unusual pattern incident

### Requirement 7: Incident Lifecycle Management

**User Story:** As a traffic monitoring operator, I want to track incidents from detection through resolution, so that incident duration and response times can be measured.

#### Acceptance Criteria

1. THE Incident_Lifecycle_Manager SHALL assign unique incident IDs using timestamp and camera identifier
2. WHEN an incident is first detected, THE Incident_Lifecycle_Manager SHALL create an incident record with state "active"
3. THE Incident_Lifecycle_Manager SHALL track incident states: active, acknowledged, responding, resolved, false_positive
4. WHEN incident conditions no longer exist for 60 seconds, THE Incident_Lifecycle_Manager SHALL transition state to "resolved"
5. THE Incident_Lifecycle_Manager SHALL calculate incident duration from first detection to resolution
6. THE Incident_Lifecycle_Manager SHALL allow manual state transitions through operator interface
7. THE Incident_Lifecycle_Manager SHALL maintain incident history with all state transitions and timestamps
8. THE Incident_Lifecycle_Manager SHALL prevent duplicate incident creation for the same location within 5 minutes

### Requirement 8: Confidence Scoring and False Positive Reduction

**User Story:** As a traffic monitoring operator, I want high-confidence incident alerts, so that I can focus on real incidents without alert fatigue.

#### Acceptance Criteria

1. THE Confidence_Scorer SHALL calculate incident confidence scores from 0.0 to 1.0 based on multiple detection factors
2. THE Confidence_Scorer SHALL weight factors including detection duration, object tracking stability, and pattern consistency
3. WHEN confidence score is below 0.6, THE Confidence_Scorer SHALL mark incident as "low confidence" and suppress immediate alerts
4. THE Confidence_Scorer SHALL increase confidence score when incident persists over time
5. THE Confidence_Scorer SHALL decrease confidence score when incident characteristics become inconsistent
6. THE Confidence_Scorer SHALL apply incident-type-specific confidence thresholds (collision: 0.75, stopped vehicle: 0.65, wrong-way: 0.80)
7. THE Confidence_Scorer SHALL track false positive rate per incident type and adjust thresholds to maintain rate below 10%

### Requirement 9: Video Clip Extraction

**User Story:** As a traffic analyst, I want to extract video clips around incident times, so that incidents can be reviewed and analyzed in detail.

#### Acceptance Criteria

1. THE Frame_Buffer SHALL maintain a circular buffer of 60 seconds of video frames per camera
2. WHEN an incident is detected, THE Video_Clip_Extractor SHALL extract video from 30 seconds before to 30 seconds after incident start
3. THE Video_Clip_Extractor SHALL encode extracted clips in H.264 format with 1920x1080 resolution
4. THE Video_Clip_Extractor SHALL annotate video clips with incident bounding boxes and tracking IDs
5. THE Video_Clip_Extractor SHALL generate clip filenames including incident ID, camera ID, and timestamp
6. THE Video_Clip_Extractor SHALL store clips in cloud storage with 30-day retention
7. THE Video_Clip_Extractor SHALL complete clip extraction within 10 seconds of incident detection
8. THE Video_Clip_Extractor SHALL generate thumbnail images at incident detection moment

### Requirement 10: Emergency Service Integration

**User Story:** As an emergency dispatcher, I want to receive incident notifications with location and details, so that emergency response can be coordinated efficiently.

#### Acceptance Criteria

1. THE Emergency_Service_Notifier SHALL send incident data to external emergency services via webhook API
2. WHEN incident severity is "critical", THE Emergency_Service_Notifier SHALL send notifications within 5 seconds
3. THE Emergency_Service_Notifier SHALL include incident type, severity, location coordinates, camera ID, and video clip URL in notifications
4. THE Emergency_Service_Notifier SHALL retry failed webhook deliveries up to 3 times with exponential backoff
5. THE Emergency_Service_Notifier SHALL support multiple webhook endpoints for different emergency service types
6. THE Emergency_Service_Notifier SHALL log all notification attempts with delivery status
7. THE Emergency_Service_Notifier SHALL provide webhook authentication using API keys or OAuth tokens
8. THE Emergency_Service_Notifier SHALL format notifications according to configurable JSON schema templates

### Requirement 11: Incident Severity Classification

**User Story:** As a traffic monitoring operator, I want incidents classified by severity, so that critical incidents receive immediate attention.

#### Acceptance Criteria

1. THE Incident_Severity_Classifier SHALL assign severity levels: minor, moderate, severe, critical
2. THE Incident_Severity_Classifier SHALL classify wrong-way driving and pedestrian-vehicle proximity as "critical"
3. THE Incident_Severity_Classifier SHALL classify collisions and stopped vehicles in active lanes as "severe"
4. THE Incident_Severity_Classifier SHALL classify stopped vehicles on shoulders and small fallen objects as "moderate"
5. THE Incident_Severity_Classifier SHALL classify unusual traffic patterns and brief slowdowns as "minor"
6. THE Incident_Severity_Classifier SHALL adjust severity based on traffic volume (higher volume increases severity)
7. THE Incident_Severity_Classifier SHALL adjust severity based on time of day (night incidents increase severity)
8. THE Incident_Severity_Classifier SHALL allow manual severity override by operators

### Requirement 12: Real-time Alert Dispatch

**User Story:** As a traffic monitoring operator, I want to receive real-time alerts for detected incidents, so that I can respond immediately.

#### Acceptance Criteria

1. WHEN an incident is detected with confidence above threshold, THE Alert_Dispatcher SHALL send alerts within 2 seconds
2. THE Alert_Dispatcher SHALL support multiple alert channels: dashboard notifications, email, SMS, webhook
3. THE Alert_Dispatcher SHALL include incident type, severity, location, confidence score, and video thumbnail in alerts
4. THE Alert_Dispatcher SHALL implement alert rate limiting to prevent more than 10 alerts per minute per camera
5. THE Alert_Dispatcher SHALL aggregate similar incidents from the same location into single alerts
6. THE Alert_Dispatcher SHALL provide alert acknowledgment functionality to mark incidents as reviewed
7. THE Alert_Dispatcher SHALL escalate unacknowledged critical incidents after 5 minutes
8. THE Alert_Dispatcher SHALL maintain alert history with acknowledgment status and response times

### Requirement 13: Geographic Incident Mapping

**User Story:** As a traffic coordinator, I want to see incidents on a geographic map, so that I can understand incident distribution and coordinate responses.

#### Acceptance Criteria

1. THE Geo_Incident_Mapper SHALL display active incidents on an interactive map interface
2. THE Geo_Incident_Mapper SHALL use camera GPS coordinates to position incidents on the map
3. THE Geo_Incident_Mapper SHALL color-code incident markers by severity (green: minor, yellow: moderate, orange: severe, red: critical)
4. WHEN an incident marker is clicked, THE Geo_Incident_Mapper SHALL display incident details and video thumbnail
5. THE Geo_Incident_Mapper SHALL show incident density heatmap for historical analysis
6. THE Geo_Incident_Mapper SHALL filter incidents by type, severity, and time range
7. THE Geo_Incident_Mapper SHALL display incident clusters when multiple incidents occur in proximity
8. THE Geo_Incident_Mapper SHALL update incident positions in real-time as new incidents are detected

### Requirement 14: Historical Incident Analysis

**User Story:** As a traffic analyst, I want to analyze historical incident data, so that I can identify patterns and improve traffic safety.

#### Acceptance Criteria

1. THE Historical_Incident_Analyzer SHALL store all incident records in the Incident_Database with full details
2. THE Historical_Incident_Analyzer SHALL generate incident reports by type, severity, location, and time period
3. THE Historical_Incident_Analyzer SHALL calculate incident frequency metrics: incidents per hour, per day, per camera
4. THE Historical_Incident_Analyzer SHALL identify incident hotspots where incidents occur frequently
5. THE Historical_Incident_Analyzer SHALL detect temporal patterns such as peak incident hours and days
6. THE Historical_Incident_Analyzer SHALL calculate average incident duration and response times
7. THE Historical_Incident_Analyzer SHALL provide incident trend analysis showing increases or decreases over time
8. THE Historical_Incident_Analyzer SHALL export incident data in CSV and JSON formats for external analysis

### Requirement 15: Configurable Sensitivity Management

**User Story:** As a system administrator, I want to configure detection sensitivity per incident type, so that detection can be tuned for different environments.

#### Acceptance Criteria

1. THE Sensitivity_Config_Manager SHALL provide configuration parameters for each incident type
2. THE Sensitivity_Config_Manager SHALL support parameters including detection thresholds, duration requirements, and confidence thresholds
3. WHEN sensitivity configuration is updated, THE Sensitivity_Config_Manager SHALL apply changes within 10 seconds without system restart
4. THE Sensitivity_Config_Manager SHALL validate configuration values to prevent invalid settings
5. THE Sensitivity_Config_Manager SHALL maintain configuration history with timestamps and user identifiers
6. THE Sensitivity_Config_Manager SHALL support per-camera sensitivity overrides for location-specific tuning
7. THE Sensitivity_Config_Manager SHALL provide preset sensitivity profiles: strict, balanced, lenient
8. THE Sensitivity_Config_Manager SHALL export and import sensitivity configurations in JSON format

### Requirement 16: Performance and Latency Requirements

**User Story:** As a system administrator, I want the incident detection system to operate with low latency, so that incidents are detected and reported in real-time.

#### Acceptance Criteria

1. THE Incident_Detector SHALL process each video frame for incident detection within 100ms
2. THE Incident_Detector SHALL detect incidents within 2 seconds of incident occurrence
3. THE Incident_Detector SHALL support simultaneous incident detection on 6 camera feeds
4. WHILE processing 6 camera feeds, THE Incident_Detector SHALL maintain CPU usage below 80%
5. THE Incident_Detector SHALL maintain GPU memory usage below 8GB for all incident detection operations
6. THE Incident_Detector SHALL process at least 15 frames per second per camera
7. THE Incident_Detector SHALL complete end-to-end incident detection and alert dispatch within 5 seconds

### Requirement 17: Database Schema and Storage

**User Story:** As a database administrator, I want a well-designed incident database schema, so that incident data can be stored efficiently and queried effectively.

#### Acceptance Criteria

1. THE Incident_Database SHALL store incident records with fields: id, type, severity, confidence, camera_id, timestamp, location, state, duration
2. THE Incident_Database SHALL store incident metadata including involved objects, tracking IDs, and detection parameters
3. THE Incident_Database SHALL index incident records by timestamp, camera_id, type, and severity for fast queries
4. THE Incident_Database SHALL support PostgreSQL for production and SQLite for development
5. THE Incident_Database SHALL implement data retention policies with configurable retention periods per incident type
6. THE Incident_Database SHALL store video clip references with cloud storage URLs
7. THE Incident_Database SHALL maintain referential integrity between incidents and related detection records
8. THE Incident_Database SHALL support concurrent read and write operations from multiple detection processes

### Requirement 18: Integration with Existing Systems

**User Story:** As a system integrator, I want the incident detection system to integrate seamlessly with existing components, so that implementation is smooth and non-disruptive.

#### Acceptance Criteria

1. THE Incident_Detector SHALL consume object detection results from existing YOLOv11 detection pipeline
2. THE Incident_Detector SHALL utilize existing Speed_Estimator for vehicle velocity data
3. THE Incident_Detector SHALL integrate with existing Alert_Manager for notification dispatch
4. THE Incident_Detector SHALL store incident data in existing PostgreSQL/SQLite database
5. THE Incident_Detector SHALL display incidents on existing analytics dashboard
6. THE Incident_Detector SHALL use existing Cloud_Storage for video clip storage
7. THE Incident_Detector SHALL leverage existing Multi_Camera_Manager for camera feed access
8. THE Incident_Detector SHALL extend existing API with incident-specific endpoints

### Requirement 19: API Endpoints for Incident Management

**User Story:** As a frontend developer, I want RESTful API endpoints for incident management, so that I can build user interfaces for incident monitoring.

#### Acceptance Criteria

1. THE Incident_API SHALL provide GET /api/incidents endpoint to list incidents with filtering by type, severity, camera, and time range
2. THE Incident_API SHALL provide GET /api/incidents/{id} endpoint to retrieve detailed incident information
3. THE Incident_API SHALL provide POST /api/incidents/{id}/acknowledge endpoint to acknowledge incidents
4. THE Incident_API SHALL provide PUT /api/incidents/{id}/state endpoint to update incident state
5. THE Incident_API SHALL provide GET /api/incidents/stats endpoint to retrieve incident statistics
6. THE Incident_API SHALL provide GET /api/incidents/map endpoint to retrieve incident data for map visualization
7. THE Incident_API SHALL provide GET /api/incidents/{id}/video endpoint to retrieve video clip URL
8. THE Incident_API SHALL provide POST /api/incidents/sensitivity endpoint to update sensitivity configuration
9. THE Incident_API SHALL return responses in JSON format with consistent error handling

### Requirement 20: Testing and Validation

**User Story:** As a quality assurance engineer, I want comprehensive testing for incident detection, so that system reliability and accuracy can be validated.

#### Acceptance Criteria

1. THE Incident_Detector SHALL achieve minimum 85% precision for collision detection on test dataset
2. THE Incident_Detector SHALL achieve minimum 80% recall for stopped vehicle detection on test dataset
3. THE Incident_Detector SHALL achieve minimum 90% precision for wrong-way detection on test dataset
4. THE Incident_Detector SHALL maintain false positive rate below 10% for all incident types
5. THE Incident_Detector SHALL process test video dataset of 100 hours within 24 hours
6. THE Incident_Detector SHALL correctly classify incident severity with 85% accuracy on labeled test data
7. THE Incident_Detector SHALL demonstrate stable performance over 72-hour continuous operation test
8. THE Incident_Detector SHALL handle camera feed interruptions without system crashes or data loss

### Requirement 21: Configuration File Parser

**User Story:** As a system administrator, I want to configure incident detection through configuration files, so that settings can be version-controlled and deployed consistently.

#### Acceptance Criteria

1. WHEN an incident detection configuration file is provided, THE Config_Parser SHALL parse incident type definitions, thresholds, and sensitivity settings
2. WHEN an invalid configuration file is provided, THE Config_Parser SHALL return descriptive error messages indicating the specific validation failure
3. THE Config_Pretty_Printer SHALL format incident configuration files with proper JSON structure and indentation
4. FOR ALL valid incident configuration objects, parsing then printing then parsing SHALL produce an equivalent configuration object (round-trip property)
5. THE Config_Parser SHALL validate threshold values are within acceptable ranges (0.0 to 1.0 for confidence, positive integers for durations)
6. THE Config_Parser SHALL support JSON configuration file format with schema validation
7. THE Config_Parser SHALL provide default values for optional configuration parameters

### Requirement 22: Incident Detection Correctness Properties

**User Story:** As a quality assurance engineer, I want to verify incident detection correctness through property-based testing, so that edge cases and invariants are validated.

#### Acceptance Criteria

1. FOR ALL detected incidents, the incident confidence score SHALL be between 0.0 and 1.0 inclusive (invariant property)
2. FOR ALL incidents with state transitions, the timestamp of the new state SHALL be greater than or equal to the timestamp of the previous state (monotonic time property)
3. FOR ALL stopped vehicle incidents, IF the vehicle resumes movement above 10 km/h, THEN the incident SHALL transition to resolved state within 5 seconds (state transition property)
4. FOR ALL collision incidents, the number of involved vehicles SHALL be at least 2 (invariant property)
5. FOR ALL video clip extractions, the clip duration SHALL be between 50 and 70 seconds (invariant property)
6. FOR ALL incidents, IF confidence score increases above threshold after initial low-confidence detection, THEN an alert SHALL be dispatched (threshold crossing property)
7. FOR ALL wrong-way incidents, the vehicle heading angle SHALL deviate by more than 135 degrees from expected flow direction (geometric invariant)
8. FOR ALL incident lifecycle states, valid state transitions SHALL follow the defined state machine: active → acknowledged → responding → resolved, with false_positive as terminal state from any state (state machine property)
